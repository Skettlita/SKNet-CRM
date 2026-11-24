import secrets

from fastapi import HTTPException

from app.auth.security import hasher
from app.auth.store import (
    IAM, audit, execute, identity_query, person_permissions, revoke_reset_tokens, revoke_sessions, row, rows,
)


def create_identity(db, realm, fields, password_hash, *, company=None, temporary=False):
    user_id = execute(db, """
        INSERT INTO core.users(name, username, email, account_scope, password_hash,
                               must_change_password, temporary_password_expires_at)
        VALUES (:name, :username, :email, :scope, :password, :temporary,
                CASE WHEN :temporary THEN now() + interval '24 hours' END)
        RETURNING id
    """, name=fields.name, username=fields.username, email=fields.email, scope=realm.code,
        password=password_hash, temporary=temporary).scalar_one()
    if realm.isp:
        person_id = execute(db, "INSERT INTO core.memberships(user_id, company_id) VALUES (:user, :company) RETURNING id",
                            user=user_id, company=company).scalar_one()
    else:
        person_id = execute(db, "INSERT INTO platform.staff(user_id) VALUES (:user) RETURNING id", user=user_id).scalar_one()
    return user_id, person_id


def tenant_filter(realm, alias=""):
    return f" AND {alias}company_id = :company" if realm.isp else ""


def role_catalog(db, realm, company):
    result = rows(db, f"""
        SELECT r.id, r.name, r.description,
               COALESCE(array_agg(p.code ORDER BY p.code) FILTER (WHERE p.code IS NOT NULL),
                        ARRAY[]::text[]) AS permissions
        FROM {realm.schema}.roles r
        LEFT JOIN {realm.schema}.role_permissions rp ON rp.role_id = r.id
        LEFT JOIN {realm.schema}.permissions p ON p.id = rp.permission_id
        WHERE true {tenant_filter(realm, "r.")}
        GROUP BY r.id ORDER BY lower(r.name), r.id
    """, company=company)
    return {r["id"]: dict(r) for r in result}


def permissions_catalog(db, realm):
    return rows(db, f"SELECT code, description FROM {realm.schema}.permissions ORDER BY code")


def role_permissions(db, realm, role_id, company, codes):
    execute(db, f"DELETE FROM {realm.schema}.role_permissions WHERE role_id = :role {tenant_filter(realm)}",
            role=role_id, company=company)
    if realm.isp:
        execute(db, """
            INSERT INTO core.role_permissions(company_id, role_id, permission_id)
            SELECT :company, :role, id FROM core.permissions WHERE code = ANY(:codes)
        """, role=role_id, company=company, codes=list(codes))
    else:
        execute(db, """
            INSERT INTO platform.role_permissions(role_id, permission_id)
            SELECT :role, id FROM platform.permissions WHERE code = ANY(:codes)
        """, role=role_id, codes=list(codes))


def create_role(db, realm, name, description, company, codes):
    if realm.isp:
        role_id = execute(db, "INSERT INTO core.roles(company_id, name, description) VALUES (:company, :name, :description) RETURNING id",
                          company=company, name=name, description=description).scalar_one()
    else:
        role_id = execute(db, "INSERT INTO platform.roles(name, description) VALUES (:name, :description) RETURNING id",
                          name=name, description=description).scalar_one()
    role_permissions(db, realm, role_id, company, codes)
    return role_id


def replace_roles(db, realm, person, company, role_ids):
    execute(db, f"DELETE FROM {realm.schema}.{realm.assignments} WHERE {realm.person_key} = :person {tenant_filter(realm)}",
            person=person, company=company)
    for role_id in set(role_ids):
        if realm.isp:
            execute(db, "INSERT INTO core.membership_roles(company_id, membership_id, role_id) VALUES (:company, :person, :role)",
                    company=company, person=person, role=role_id)
        else:
            execute(db, "INSERT INTO platform.staff_roles(staff_id, role_id) VALUES (:person, :role)",
                    person=person, role=role_id)


def user_list(db, realm, company, search, offset, limit):
    return rows(db, f"""
        SELECT u.id, u.name, u.username, u.email, (u.active AND p.active) AS active,
               u.must_change_password,
               ARRAY(SELECT a.role_id FROM {realm.schema}.{realm.assignments} a
                     WHERE a.{realm.person_key} = p.id ORDER BY a.role_id) AS role_ids
        FROM {realm.schema}.{realm.people} p JOIN core.users u ON u.id = p.user_id
        WHERE u.account_scope = :scope {tenant_filter(realm, "p.")}
          AND (:search = '' OR strpos(lower(u.name || ' ' || u.username || ' ' || u.email), lower(:search)) > 0)
        ORDER BY lower(u.name), u.id OFFSET :offset LIMIT :limit
    """, scope=realm.code, company=company, search=search, offset=offset, limit=limit)


def target_user(db, principal, user_id):
    realm = principal.realm
    record = row(db, identity_query(realm) + f" AND u.id = :id {tenant_filter(realm, 'p.')}",
                 scope=realm.code, id=user_id, company=principal.company)
    if record is None:
        raise HTTPException(404, "Cuenta no encontrada.")
    return record


def assignable(db, principal, role_ids):
    roles = role_catalog(db, principal.realm, principal.company)
    for role_id in set(role_ids):
        if role_id not in roles:
            raise HTTPException(404, "Rol no encontrado.")
        require_subset(principal, roles[role_id]["permissions"])


def require_subset(principal, codes):
    if not set(codes).issubset(principal.permissions):
        raise HTTPException(403, "No puedes administrar permisos que no tienes.")


def require_manageable(db, principal, target):
    require_subset(principal, person_permissions(db, principal.realm, target["person_id"]))


def ensure_admin_remains(db, realm, company):
    result = execute(db, f"""
        SELECT EXISTS (
            SELECT 1
            FROM {realm.schema}.{realm.people} p JOIN core.users u ON u.id = p.user_id
            JOIN {realm.schema}.{realm.assignments} a ON a.{realm.person_key} = p.id
            JOIN {realm.schema}.role_permissions rp ON rp.role_id = a.role_id
            JOIN {realm.schema}.permissions perm ON perm.id = rp.permission_id
            WHERE p.active AND u.active {tenant_filter(realm, "p.")}
              AND perm.code = ANY(:required)
              AND NOT u.must_change_password
            GROUP BY p.id HAVING count(DISTINCT perm.code) = :amount
        )
    """, company=company, required=sorted(IAM), amount=len(IAM)).scalar_one()
    if not result:
        raise HTTPException(409, "Debe quedar al menos un administrador habilitado para gestionar el acceso.")


def enforce_user_limit(db, principal):
    limit = principal.plan["max_users"] if principal.plan else None
    if limit is None:
        return
    active = execute(db, """
        SELECT count(*) FROM core.memberships m JOIN core.users u ON u.id = m.user_id
        WHERE m.company_id = :company AND m.active AND u.active
    """, company=principal.company).scalar_one()
    if active >= limit:
        raise HTTPException(409, "El plan alcanzó su límite de usuarios activos.")


def issue_temporary(db, user, *, actor, reason):
    temporary = secrets.token_urlsafe(24)
    execute(db, """
        UPDATE core.users SET password_hash = :password, must_change_password = true,
            temporary_password_expires_at = now() + interval '24 hours',
            temporary_password_used_at = NULL, updated_at = now()
        WHERE id = :id
    """, id=user["id"], password=hasher.hash(temporary))
    revoke_sessions(db, user["id"])
    revoke_reset_tokens(db, user["id"])
    audit(db, "password.reset", "user", user["id"], actor=actor, company=user["company_id"], reason=reason)
    return temporary
