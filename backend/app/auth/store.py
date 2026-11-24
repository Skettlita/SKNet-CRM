import json
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Realm:
    code: str
    schema: str
    people: str
    assignments: str
    person_key: str

    @property
    def isp(self) -> bool:
        return self.code == "ISP"

    @property
    def cookie(self) -> str:
        return "sknet_isp" if self.isp else "sknet_saas"

    @property
    def path(self) -> str:
        return "/api/v1/isp" if self.isp else "/api/v1/admin"


ISP = Realm("ISP", "core", "memberships", "membership_roles", "membership_id")
SAAS = Realm("SAAS", "platform", "staff", "staff_roles", "staff_id")
IAM = frozenset({"users.read", "users.write", "users.reset", "roles.read", "roles.write"})


def execute(db: Session, statement: str, **values):
    return db.execute(text(statement), values)


def rows(db: Session, statement: str, **values):
    return execute(db, statement, **values).mappings().all()


def row(db: Session, statement: str, **values):
    return execute(db, statement, **values).mappings().one_or_none()


def access_lock(db: Session) -> None:
    # Serialize IAM mutations so that permission checks and last-admin checks see one state.
    execute(db, "SELECT pg_advisory_xact_lock(52773, 2)")


def audit(db, action, entity_type, entity_id, *, actor=None, company=None, before=None, after=None, reason=None):
    execute(
        db,
        """
        INSERT INTO audit.events(actor_user_id, company_id, action, entity_type, entity_id,
                                 before_data, after_data, reason)
        VALUES (:actor, :company, :action, :entity_type, :entity_id,
                CAST(:before AS jsonb), CAST(:after AS jsonb), :reason)
        """,
        actor=actor, company=company, action=action, entity_type=entity_type, entity_id=entity_id,
        before=json.dumps(before, default=str) if before is not None else None,
        after=json.dumps(after, default=str) if after is not None else None,
        reason=reason,
    )


def identity_query(realm: Realm) -> str:
    company_columns = "p.company_id, c.name AS company_name, c.status AS company_status" if realm.isp else (
        "NULL::uuid AS company_id, NULL::text AS company_name, 'ACTIVE' AS company_status"
    )
    company_join = "JOIN core.companies c ON c.id = p.company_id" if realm.isp else ""
    return f"""
        SELECT u.id, u.name, u.username, u.email, u.active, u.password_hash, u.must_change_password,
               u.temporary_password_expires_at, u.email_verified_at, u.compact_view,
               p.id AS person_id, p.active AS affiliation_active, {company_columns}
        FROM {realm.schema}.{realm.people} p JOIN core.users u ON u.id = p.user_id
        {company_join}
        WHERE u.account_scope = :scope
    """


def find_identity(db, realm, identifier):
    column = "email" if "@" in identifier else "username"
    return row(db, identity_query(realm) + f" AND lower(u.{column}) = :identifier",
               scope=realm.code, identifier=identifier.strip().lower())


def person_permissions(db, realm, person_id):
    result = execute(
        db, f"""
        SELECT DISTINCT perm.code
        FROM {realm.schema}.{realm.assignments} a
        JOIN {realm.schema}.role_permissions rp ON rp.role_id = a.role_id
        JOIN {realm.schema}.permissions perm ON perm.id = rp.permission_id
        WHERE a.{realm.person_key} = :person
        """, person=person_id,
    )
    return set(result.scalars())


def subscription(db, company):
    return row(db, """
        SELECT s.status, s.ends_at, v.max_users, v.max_clients, v.max_devices, v.min_poll_interval_seconds, p.code, v.version,
               (s.status IN ('TRIAL', 'ACTIVE', 'GRACE')
                 AND s.starts_at <= now()
                 AND (s.ends_at IS NULL OR s.ends_at > now())) AS current,
               EXISTS (
                   SELECT 1 FROM platform.plan_features pf JOIN platform.features f ON f.id = pf.feature_id
                   WHERE pf.plan_version_id = v.id AND f.code = 'ACCESS' AND f.implemented
               ) AS access_enabled,
               ARRAY(
                   SELECT f.code FROM platform.plan_features pf JOIN platform.features f ON f.id = pf.feature_id
                   WHERE pf.plan_version_id = v.id AND f.implemented ORDER BY f.code
               ) AS enabled_features
        FROM platform.subscriptions s JOIN platform.plan_versions v ON v.id = s.plan_version_id
        JOIN platform.plans p ON p.id = v.plan_id
        WHERE s.company_id = :company AND s.status <> 'CANCELLED'
        """, company=company)


@dataclass(frozen=True)
class Principal:
    realm: Realm
    user: object
    permissions: set[str]
    plan: object
    session_id: UUID
    grants: set[str]

    @property
    def company(self):
        return self.user["company_id"]

    @property
    def id(self):
        return self.user["id"]

    @property
    def changing_password(self) -> bool:
        return self.user["must_change_password"]

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise HTTPException(403, "No tienes permiso para esta acción.")


def public_identity(principal: Principal) -> dict:
    account = {key: principal.user[key] for key in (
        "id", "name", "username", "email", "company_id", "company_name",
        "compact_view", "must_change_password",
    )}
    return {**account, "permissions": sorted(principal.permissions),
            "plan": dict(principal.plan) if principal.plan is not None else None}


def revoke_sessions(db, user_id):
    execute(db, "UPDATE core.sessions SET revoked_at = now() WHERE user_id = :user AND revoked_at IS NULL",
            user=user_id)


def revoke_reset_tokens(db, user_id):
    execute(db, """
        UPDATE core.password_reset_tokens SET revoked_at = now()
        WHERE user_id = :user AND used_at IS NULL AND revoked_at IS NULL
        """, user=user_id)
