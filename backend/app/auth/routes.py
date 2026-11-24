import os
import secrets
from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from sqlalchemy.exc import IntegrityError

from app.auth import accounts, onboarding, recovery, schemas
from app.auth.security import (
    BAD_CREDENTIALS, check_origin, create_session, dummy_hash, hasher, identity_active, principal,
    reserve_attempt, session_cookie, temporary_expired, verify,
)
from app.auth.store import (
    ISP, SAAS, access_lock, audit, execute, find_identity, public_identity, revoke_reset_tokens, revoke_sessions,
)


@contextmanager
def write_operation(db):
    access_lock(db)
    try:
        yield
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise HTTPException(409, "El nombre de usuario, correo o nombre de rol ya está en uso.") from None
        raise


def database(request):
    return request.state.database()


def scoped_router(realm):
    router = APIRouter(prefix=realm.path, tags=["ISP" if realm.isp else "SaaS"])

    @router.post("/login")
    def login(data: schemas.Login, request: Request, response: Response):
        check_origin(request)
        identifier = data.identifier.lower()
        with database(request) as db:
            bucket = reserve_attempt(db, request, realm, "login", identifier)
            candidate = find_identity(db, realm, identifier)
            encoded = candidate["password_hash"] if candidate else dummy_hash
            correct = verify(encoded, data.password)
            if not correct or not identity_active(candidate) or temporary_expired(candidate):
                raise HTTPException(401, BAD_CREDENTIALS)

            with write_operation(db):
                candidate = find_identity(db, realm, identifier)
                if not identity_active(candidate) or candidate["password_hash"] != encoded or temporary_expired(candidate):
                    raise HTTPException(401, BAD_CREDENTIALS)
                if candidate["must_change_password"]:
                    used = execute(db, """
                        UPDATE core.users SET temporary_password_used_at = now()
                        WHERE id = :user AND temporary_password_used_at IS NULL RETURNING id
                    """, user=candidate["id"]).scalar()
                    if not used:
                        raise HTTPException(401, BAD_CREDENTIALS)
                    revoke_sessions(db, candidate["id"])
                if hasher.check_needs_rehash(encoded):
                    execute(db, "UPDATE core.users SET password_hash = :hash WHERE id = :id",
                            hash=hasher.hash(data.password), id=candidate["id"])
                execute(db, "UPDATE core.users SET last_login_at = now() WHERE id = :id", id=candidate["id"])
                execute(db, "DELETE FROM core.auth_attempts WHERE bucket = :bucket", bucket=bucket)
                token = create_session(db, realm, candidate["id"])
        session_cookie(request, response, realm, token)
        return {"must_change_password": candidate["must_change_password"]}

    @router.get("/me")
    def me(request: Request):
        with database(request) as db:
            actor = principal(db, request, realm)
            return {
                **public_identity(actor),
                "email_verified": actor.user["email_verified_at"] is not None,
                "email_verification_available": recovery.mail_enabled(),
            }

    @router.post("/profile/verify-email", status_code=202)
    def send_verification(request: Request, background: BackgroundTasks):
        origin = check_origin(request)
        if not recovery.mail_enabled():
            raise HTTPException(503, "La verificación por correo no está configurada.")
        with database(request) as db:
            account = principal(db, request, realm)
            reserve_attempt(db, request, realm, "request-verification", str(account.id))
            with write_operation(db):
                actor = principal(db, request, realm)
                if actor.changing_password:
                    raise HTTPException(403, "Cambia tu contraseña temporal primero.")
                if actor.user["email_verified_at"] is None:
                    token = recovery.issue_link(db, actor.id, "verify")
                    prefix = "" if realm.isp else "/admin"
                    background.add_task(recovery.send_access_link, actor.user["email"], origin + prefix, token, "verify")
        return {"ok": True}

    @router.post("/verify")
    def verify_email(data: schemas.VerifyEmail, request: Request):
        check_origin(request)
        with database(request) as db:
            reserve_attempt(db, request, realm, "verify", "")
            with write_operation(db):
                recovery.consume_link(db, realm, data.token, "verify")
        return {"ok": True}


    @router.put("/profile")
    def update_profile(data: schemas.ProfileWrite, request: Request):
        check_origin(request)
        with database(request) as db, write_operation(db):
            actor = principal(db, request, realm)
            if actor.changing_password:
                raise HTTPException(403, "Cambia tu contraseña temporal primero.")
            execute(db, """
                UPDATE core.users SET name = :name, compact_view = :compact, updated_at = now()
                WHERE id = :id
            """, id=actor.id, name=data.name, compact=data.compact_view)
            audit(db, "profile.update", "user", actor.id, actor=actor.id, company=actor.company,
                  before={"name": actor.user["name"], "compact_view": actor.user["compact_view"]},
                  after=data.model_dump())
            return {"ok": True}

    @router.post("/logout", status_code=204)
    def logout(request: Request, response: Response):
        check_origin(request)
        with database(request) as db, write_operation(db):
            actor = principal(db, request, realm)
            execute(db, "UPDATE core.sessions SET revoked_at = now() WHERE id = :id",
                    id=actor.session_id)
        response.delete_cookie(realm.cookie, path=realm.path, httponly=True, samesite="strict",
                               secure=request.url.scheme == "https" or os.getenv("SKNET_COOKIE_SECURE") == "1")

    @router.post("/password")
    def change_password(data: schemas.ChangePassword, request: Request, response: Response):
        check_origin(request)
        with database(request) as db:
            first = principal(db, request, realm)
            reserve_attempt(db, request, realm, "change-password", str(first.id))
            encoded = first.user["password_hash"]
            if not verify(encoded, data.current_password):
                raise HTTPException(400, "La contraseña actual es incorrecta.")
            if data.current_password == data.password:
                raise HTTPException(400, "Elige una contraseña diferente.")
            replacement = hasher.hash(data.password)
            with write_operation(db):
                actor = principal(db, request, realm)
                if actor.user["password_hash"] != encoded:
                    raise HTTPException(409, "La contraseña cambió. Inicia sesión nuevamente.")
                execute(db, """
                    UPDATE core.users SET password_hash = :password, must_change_password = false,
                        temporary_password_expires_at = NULL, temporary_password_used_at = NULL, updated_at = now()
                    WHERE id = :id
                """, id=actor.id, password=replacement)
                revoke_sessions(db, actor.id)
                revoke_reset_tokens(db, actor.id)
                audit(db, "password.change", "user", actor.id, actor=actor.id, company=actor.company)
                token = create_session(db, realm, actor.id)
        session_cookie(request, response, realm, token)
        return {"ok": True}

    @router.get("/users")
    def list_users(request: Request, q: str = Query("", max_length=120),
                   offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
        with database(request) as db:
            actor = principal(db, request, realm)
            actor.require("users.read")
            data = accounts.user_list(db, realm, actor.company, q.strip(), offset, limit + 1)
            can_manage = bool({"users.write", "users.reset"} & actor.permissions)
            roles = accounts.role_catalog(db, realm, actor.company) if can_manage else {}
            result = []
            for user in data[:limit]:
                editable = False
                resettable = False
                if can_manage:
                    effective = {code for role_id in user["role_ids"] for code in roles[role_id]["permissions"]}
                    subset = effective.issubset(actor.grants)
                    editable = subset and "users.write" in actor.permissions
                    resettable = subset and "users.reset" in actor.permissions and user["id"] != actor.id and user["active"]
                entry = dict(user)
                if "roles.read" not in actor.permissions:
                    entry.pop("role_ids")
                result.append({**entry, "editable": editable, "resettable": resettable})
            return {"items": result, "has_more": len(data) > limit}

    @router.post("/users", status_code=201)
    def create_user(data: schemas.UserWrite, request: Request):
        check_origin(request)
        with database(request) as db, write_operation(db):
            actor = principal(db, request, realm)
            actor.require("users.write")
            if data.role_ids:
                actor.require("roles.read")
                accounts.assignable(db, actor, data.role_ids)
            accounts.enforce_user_limit(db, actor)
            temporary = secrets.token_urlsafe(24)
            user_id, person_id = accounts.create_identity(db, realm, data, hasher.hash(temporary),
                                                          company=actor.company, temporary=True)
            accounts.replace_roles(db, realm, person_id, actor.company, data.role_ids)
            audit(db, "user.create", "user", user_id, actor=actor.id, company=actor.company,
                  after={"active": True, "role_ids": data.role_ids})
            return {"id": user_id, "temporary_password": temporary}

    @router.put("/users/{user_id}")
    def edit_user(user_id: UUID, data: schemas.UserEdit, request: Request):
        check_origin(request)
        with database(request) as db, write_operation(db):
            actor = principal(db, request, realm)
            actor.require("users.write")
            target = accounts.target_user(db, actor, user_id)
            accounts.require_manageable(db, actor, target)
            same_user = user_id == actor.id
            if same_user and (not data.active or data.role_ids is not None):
                raise HTTPException(403, "Usa tu perfil para editar tus datos. Tu acceso solo lo puede cambiar otro administrador.")
            if data.role_ids is not None:
                actor.require("roles.read")
                accounts.assignable(db, actor, data.role_ids)
                accounts.replace_roles(db, realm, target["person_id"], actor.company, data.role_ids)
            if data.active and (not target["active"] or not target["affiliation_active"]):
                accounts.enforce_user_limit(db, actor)
            email_changed = data.email != target["email"]
            execute(db, """
                UPDATE core.users SET name = :name, username = :username, email = :email, active = :active,
                    email_verified_at = CASE WHEN :email_changed THEN NULL ELSE email_verified_at END,
                    updated_at = now() WHERE id = :id
            """, id=user_id, name=data.name, username=data.username, email=data.email,
                    active=data.active, email_changed=email_changed)
            execute(db, f"UPDATE {realm.schema}.{realm.people} SET active = :active WHERE id = :id",
                    active=data.active, id=target["person_id"])
            accounts.ensure_admin_remains(db, realm, actor.company)
            if not data.active or email_changed:
                revoke_sessions(db, user_id)
                revoke_reset_tokens(db, user_id)
            audit(db, "user.update", "user", user_id, actor=actor.id, company=actor.company,
                  before={"active": target["active"] and target["affiliation_active"]},
                  after={"active": data.active, "role_ids": data.role_ids})
            return {"ok": True}

    @router.post("/users/{user_id}/reset")
    def reset_user(user_id: UUID, request: Request):
        check_origin(request)
        with database(request) as db, write_operation(db):
            actor = principal(db, request, realm)
            actor.require("users.reset")
            target = accounts.target_user(db, actor, user_id)
            accounts.require_manageable(db, actor, target)
            if user_id == actor.id or not identity_active(target):
                raise HTTPException(409, "El restablecimiento requiere otra cuenta activa.")
            temporary = accounts.issue_temporary(db, target, actor=actor.id, reason="Restablecimiento administrativo")
            accounts.ensure_admin_remains(db, realm, actor.company)
            return {"temporary_password": temporary}

    @router.get("/roles")
    def list_roles(request: Request):
        with database(request) as db:
            actor = principal(db, request, realm)
            actor.require("roles.read")
            result = accounts.role_catalog(db, realm, actor.company)
            return {
                "items": [{**role,
                           "assignable": set(role["permissions"]).issubset(actor.grants),
                           "editable": "roles.write" in actor.permissions and set(role["permissions"]).issubset(actor.grants)}
                          for role in result.values()],
                "permissions": accounts.permissions_catalog(db, realm),
                "delegable": sorted(actor.grants),
            }

    def save_role(data, request, role_id=None):
        check_origin(request)
        with database(request) as db, write_operation(db):
            actor = principal(db, request, realm)
            actor.require("roles.write")
            codes = set(data.permissions)
            accounts.require_subset(actor, codes)
            previous = None
            if role_id is None:
                role_id = accounts.create_role(db, realm, data.name, data.description, actor.company, codes)
            else:
                previous = accounts.role_catalog(db, realm, actor.company).get(role_id)
                if previous is None:
                    raise HTTPException(404, "Rol no encontrado.")
                accounts.require_subset(actor, previous["permissions"])
                execute(db, f"""UPDATE {realm.schema}.roles SET name = :name, description = :description
                                WHERE id = :id {accounts.tenant_filter(realm)}""",
                        id=role_id, name=data.name, description=data.description, company=actor.company)
                accounts.role_permissions(db, realm, role_id, actor.company, codes)
                accounts.ensure_admin_remains(db, realm, actor.company)
            audit(db, "role.update" if previous else "role.create", "role", role_id,
                  actor=actor.id, company=actor.company, before=previous,
                  after={"name": data.name, "permissions": sorted(codes)})
            return {"id": role_id}

    @router.post("/roles", status_code=201)
    def add_role(data: schemas.RoleWrite, request: Request):
        return save_role(data, request)

    @router.put("/roles/{role_id}")
    def edit_role(role_id: UUID, data: schemas.RoleWrite, request: Request):
        return save_role(data, request, role_id)

    return router


isp = scoped_router(ISP)
admin = scoped_router(SAAS)


@isp.get("/signup")
def signup_status(request: Request):
    with database(request) as db:
        config = onboarding.settings(db)
        enabled = config["public_signup_enabled"] and config["active"]
        return {"enabled": enabled, "plan": ({
                    "version_id": config["id"], "name": config["name"], "price": config["monthly_price"],
                    "currency": config["currency"], "billing_period": config["billing_period"],
                    "duration_days": config["trial_days"],
                } if enabled else None),
                "terms_version": "2026-11-24"}


@isp.post("/signup", status_code=201)
def signup(data: schemas.Signup, request: Request, background: BackgroundTasks):
    origin = check_origin(request)
    if not data.accept_terms:
        raise HTTPException(422, "Debes aceptar las condiciones de registro.")
    with database(request) as db:
        reserve_attempt(db, request, ISP, "signup", data.email)
        if not onboarding.settings(db)["public_signup_enabled"]:
            raise HTTPException(403, "El registro público no está habilitado.")
        replacement = hasher.hash(data.password)
        with write_operation(db):
            registered = onboarding.register_company(db, data, replacement)
            audit(db, "terms.accept", "company", registered["company_id"], company=registered["company_id"],
                  actor=registered["user_id"], after={"version": "2026-11-24"})
            if recovery.mail_enabled():
                token = recovery.issue_link(db, registered["user_id"], "verify")
                background.add_task(recovery.send_access_link, data.email, origin, token, "verify")
        return registered


@isp.get("/recover")
def recovery_status():
    return {"email_enabled": recovery.mail_enabled()}


@isp.post("/recover", status_code=202)
def request_recovery(data: schemas.RequestReset, request: Request, background: BackgroundTasks):
    origin = check_origin(request)
    with database(request) as db:
        reserve_attempt(db, request, ISP, "recover", data.email)
        if recovery.mail_enabled():
            with write_operation(db):
                candidate = find_identity(db, ISP, data.email)
                if identity_active(candidate):
                    token = recovery.issue_link(db, candidate["id"], "reset")
                    background.add_task(recovery.send_access_link, candidate["email"], origin, token, "reset")
    return {"ok": True}


@isp.post("/recover/confirm")
def confirm_recovery(data: schemas.ConfirmReset, request: Request):
    check_origin(request)
    with database(request) as db:
        reserve_attempt(db, request, ISP, "confirm", "")
        with write_operation(db):
            recovery.consume_link(db, ISP, data.token, "reset", data.password)
    return {"ok": True}


@admin.get("/settings")
def get_settings(request: Request):
    with database(request) as db:
        actor = principal(db, request, SAAS)
        actor.require("settings.read")
        return onboarding.settings(db)


@admin.put("/settings")
def change_settings(data: schemas.SettingsWrite, request: Request):
    check_origin(request)
    with database(request) as db, write_operation(db):
        actor = principal(db, request, SAAS)
        actor.require("settings.write")
        return onboarding.update_settings(db, actor, data)


@admin.post("/companies", status_code=201)
def create_company(data: schemas.CompanyRegistration, request: Request):
    check_origin(request)
    with database(request) as db, write_operation(db):
        actor = principal(db, request, SAAS)
        actor.require("companies.create")
        return onboarding.register_company(db, data, hasher.hash(data.password), actor=actor.id)


@admin.post("/support/reset")
def verified_support_reset(data: schemas.SupportReset, request: Request):
    check_origin(request)
    with database(request) as db, write_operation(db):
        actor = principal(db, request, SAAS)
        actor.require("support.reset")
        if not data.identity_verified:
            raise HTTPException(422, "Verifica la identidad antes de restablecer el acceso.")
        target = find_identity(db, ISP, data.identifier)
        if not identity_active(target):
            raise HTTPException(404, "Cuenta ISP activa no encontrada.")
        return {"temporary_password": accounts.issue_temporary(db, target, actor=actor.id, reason=data.reason)}
