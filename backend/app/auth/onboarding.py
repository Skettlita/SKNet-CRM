from fastapi import HTTPException

from app.auth.accounts import create_identity, create_role, permissions_catalog, replace_roles
from app.auth.store import ISP, SAAS, audit, execute, row
from app.platform.plans import insert_version, selected_version
from app.platform.subscriptions import start_subscription


def bootstrap_admin(db, fields, password_hash):
    if execute(db, "SELECT EXISTS (SELECT 1 FROM platform.staff)").scalar_one():
        raise HTTPException(409, "El administrador inicial ya fue creado.")
    codes = [p["code"] for p in permissions_catalog(db, SAAS)]
    role_id = create_role(db, SAAS, "Administración inicial", "Gestión inicial de la plataforma", None, codes)
    user_id, staff_id = create_identity(db, SAAS, fields, password_hash)
    replace_roles(db, SAAS, staff_id, None, [role_id])
    audit(db, "admin.bootstrap", "user", user_id, actor=user_id)
    return user_id


def settings(db):
    result = row(db, """
        SELECT s.public_signup_enabled, v.id, v.plan_id, v.version, v.monthly_price,
               v.trial_days, v.max_users, v.currency, v.billing_period, p.code, p.name, p.active
        FROM platform.settings s JOIN platform.plan_versions v ON v.id = s.default_plan_version_id
        JOIN platform.plans p ON p.id = v.plan_id WHERE s.singleton
    """)
    if not result:
        raise HTTPException(503, "La configuración de la plataforma no está disponible.")
    return dict(result)


def update_settings(db, principal, data):
    current = settings(db)
    version = selected_version(db, data.default_plan_version_id or current["id"])
    version_id = version["version_id"]

    # Preserve the Phase 2 API for clients that update default terms inline.
    legacy_fields = {"monthly_price": "price", "trial_days": "duration_days", "max_users": "max_users"}
    overrides = {
        new: getattr(data, old) for old, new in legacy_fields.items() if old in data.model_fields_set
    }
    if "price" in overrides and overrides["price"] is None:
        raise HTTPException(422, "El precio es obligatorio cuando se modifica.")
    if any(version[key] != value for key, value in overrides.items()):
        keys = ("description", "price", "currency", "billing_period", "duration_days", "max_users",
                "max_clients", "max_devices", "min_poll_interval_seconds", "retention_days")
        terms = {key: version[key] for key in keys} | overrides
        version_id = insert_version(db, version["id"], terms, version["features"])

    execute(db, """
        UPDATE platform.settings SET public_signup_enabled = :enabled,
            default_plan_version_id = :version, updated_at = now() WHERE singleton
    """, enabled=data.public_signup_enabled, version=version_id)
    updated = settings(db)
    audit(db, "settings.update", "platform_settings", None, actor=principal.id, before=current, after=updated)
    return updated


def register_company(db, fields, password_hash, *, actor=None):
    config = settings(db)
    if not config["public_signup_enabled"] and actor is None:
        raise HTTPException(403, "El registro público no está habilitado.")
    expected = getattr(fields, "expected_plan_version_id", None)
    if expected is not None and expected != config["id"]:
        raise HTTPException(409, "El plan de registro cambió. Recarga la página para revisar las condiciones.")
    version = selected_version(db, config["id"])
    company = execute(db, """
        INSERT INTO core.companies(name, tax_id, phone, email)
        VALUES (:name, :tax_id, :phone, :email) RETURNING id
    """, name=fields.company, tax_id=fields.tax_id or None, phone=fields.phone, email=fields.email).scalar_one()
    user_id, member_id = create_identity(db, ISP, fields, password_hash, company=company)
    codes = [p["code"] for p in permissions_catalog(db, ISP)]
    role_id = create_role(db, ISP, "Administración", "Administración inicial de la empresa", company, codes)
    replace_roles(db, ISP, member_id, company, [role_id])
    subscription = start_subscription(
        db, company, version, actor or user_id, status="TRIAL" if version["code"] == "TRIAL" else "ACTIVE",
        reason="Suscripción inicial de la empresa",
    )
    audit(db, "company.register", "company", company, company=company, actor=actor or user_id,
          after={"plan_version": config["version"], "subscription_id": subscription["id"], "administrator_id": user_id})
    return {"company_id": company, "user_id": user_id}
