from fastapi import HTTPException

from app.auth.accounts import create_identity, create_role, permissions_catalog, replace_roles
from app.auth.store import ISP, SAAS, audit, execute, row


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
               v.trial_days, v.max_users, p.code, p.active
        FROM platform.settings s JOIN platform.plan_versions v ON v.id = s.default_plan_version_id
        JOIN platform.plans p ON p.id = v.plan_id WHERE s.singleton
    """)
    if not result:
        raise HTTPException(503, "La configuración de la plataforma no está disponible.")
    return dict(result)


def update_settings(db, principal, data):
    current = settings(db)
    version_id = current["id"]
    plan_fields = ("monthly_price", "trial_days", "max_users")
    if any(current[key] != getattr(data, key) for key in plan_fields):
        version_id = execute(db, """
            INSERT INTO platform.plan_versions(plan_id, version, monthly_price, currency, trial_days,
                max_users, max_clients, max_devices, min_poll_interval_seconds, retention_days)
            SELECT v.plan_id, (SELECT max(version) + 1 FROM platform.plan_versions WHERE plan_id = v.plan_id),
                :price, v.currency, :days, :users, v.max_clients, v.max_devices,
                v.min_poll_interval_seconds, v.retention_days
            FROM platform.plan_versions v WHERE v.id = :current
            RETURNING id
        """, current=current["id"], price=data.monthly_price, days=data.trial_days, users=data.max_users).scalar_one()
        execute(db, """
            INSERT INTO platform.plan_features(plan_version_id, feature_id)
            SELECT :new, feature_id FROM platform.plan_features WHERE plan_version_id = :previous
        """, new=version_id, previous=current["id"])
    execute(db, """
        UPDATE platform.settings SET public_signup_enabled = :enabled,
            default_plan_version_id = :version, updated_at = now() WHERE singleton
    """, enabled=data.public_signup_enabled, version=version_id)
    updated = settings(db)
    audit(db, "settings.update", "platform_settings", None, actor=principal.id, before=current, after=updated)
    return updated


def register_company(db, fields, password_hash, *, actor=None):
    config = settings(db)
    if not config["active"] or not config["public_signup_enabled"] and actor is None:
        raise HTTPException(403, "El registro público no está habilitado.")
    company = execute(db, """
        INSERT INTO core.companies(name, tax_id, phone, email)
        VALUES (:name, :tax_id, :phone, :email) RETURNING id
    """, name=fields.company, tax_id=fields.tax_id or None, phone=fields.phone, email=fields.email).scalar_one()
    user_id, member_id = create_identity(db, ISP, fields, password_hash, company=company)
    codes = [p["code"] for p in permissions_catalog(db, ISP)]
    role_id = create_role(db, ISP, "Administración", "Administración inicial de la empresa", company, codes)
    replace_roles(db, ISP, member_id, company, [role_id])
    subscription_id = execute(db, """
        INSERT INTO platform.subscriptions(company_id, plan_version_id, ends_at)
        SELECT :company, id, CASE WHEN trial_days IS NOT NULL
               THEN now() + make_interval(days => trial_days) END
        FROM platform.plan_versions WHERE id = :version RETURNING id
    """, company=company, version=config["id"]).scalar_one()
    audit(db, "company.register", "company", company, company=company, actor=actor or user_id,
          after={"plan_version": config["version"], "subscription_id": subscription_id, "administrator_id": user_id})
    return {"company_id": company, "user_id": user_id}
