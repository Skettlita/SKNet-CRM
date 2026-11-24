from fastapi import HTTPException

from app.auth.store import audit, execute, row, rows
from app.connectivity.config import stale_seconds


FIELDS = """
    c.id, c.name, c.tax_id, c.email, c.phone, c.timezone, c.status, c.created_at,
    p.name AS plan_name, p.code AS plan_code, s.status AS subscription_status,
    collector.provisioning_status,
    CASE WHEN collector.id IS NULL THEN 'UNCONFIGURED'
         WHEN NOT collector.enabled OR (vpn.id IS NOT NULL AND NOT vpn.enabled) THEN 'DISABLED'
         WHEN collector.simulated THEN 'SIMULATED'
         WHEN collector.last_heartbeat_at IS NULL THEN 'UNKNOWN'
         WHEN collector.last_heartbeat_at <= now() - make_interval(secs=>:stale) THEN 'STALE'
         WHEN vpn.last_probe_at IS NULL OR vpn.last_probe_at <= now() - make_interval(secs=>:stale) THEN 'UNKNOWN'
         ELSE vpn.connection_status END AS connectivity
"""
JOIN = """
    FROM core.companies c
    LEFT JOIN platform.subscriptions s ON s.company_id = c.id AND s.status <> 'CANCELLED'
    LEFT JOIN platform.plan_versions v ON v.id = s.plan_version_id
    LEFT JOIN platform.plans p ON p.id = v.plan_id
    LEFT JOIN connectivity.collectors collector ON collector.company_id = c.id AND collector.retired_at IS NULL
    LEFT JOIN connectivity.vpn_tunnels vpn ON vpn.company_id = c.id AND vpn.collector_id = collector.id
        AND vpn.retired_at IS NULL
"""
SORT = {"name": "lower(c.name)", "created": "c.created_at", "status": "c.status"}


def list_companies(db, search, status, sort, direction, offset, limit):
    order = SORT[sort]
    descending = "DESC" if direction == "desc" else "ASC"
    return rows(db, f"""
        SELECT {FIELDS} {JOIN}
        WHERE (CAST(:status AS text) IS NULL OR c.status = :status)
          AND strpos(lower(concat_ws(' ', c.name,c.tax_id,c.email,c.phone)),lower(:search)) > 0
        ORDER BY {order} {descending}, c.id OFFSET :offset LIMIT :limit
    """, search=search, status=status, offset=offset, limit=limit, stale=stale_seconds())


def company(db, company_id):
    entry = row(db, f"SELECT {FIELDS} {JOIN} WHERE c.id = :id", id=company_id, stale=stale_seconds())
    if entry is None:
        raise HTTPException(404, "Empresa no encontrada.")
    return entry


def edit(db, actor, company_id, fields):
    previous = company(db, company_id)
    updated = fields.model_dump()
    updated["tax_id"] = updated["tax_id"] or None
    execute(db, """
        UPDATE core.companies SET name=:name,tax_id=:tax_id,email=:email,phone=:phone,timezone=:timezone
        WHERE id=:id
    """, id=company_id, **updated)
    audit(db, "company.update", "company", company_id, actor=actor.id, company=company_id,
          before={key: previous[key] for key in updated}, after=updated)
    return company(db, company_id)


def set_status(db, actor, company_id, fields):
    current = company(db, company_id)
    if current["status"] == "CLOSED":
        raise HTTPException(409, "Una empresa cerrada queda disponible para consulta.")
    if current["status"] != fields.status:
        execute(db, "UPDATE core.companies SET status = :status WHERE id = :id",
                status=fields.status, id=company_id)
        if fields.status == "INACTIVE":
            for table in ("sessions", "password_reset_tokens"):
                execute(db, f"""
                    UPDATE core.{table} SET revoked_at=now()
                    WHERE revoked_at IS NULL AND user_id IN (
                        SELECT user_id FROM core.memberships WHERE company_id=:company
                    )
                """, company=company_id)
        audit(db, "company.status", "company", company_id, actor=actor.id, company=company_id,
              before={"status": current["status"]}, after={"status": fields.status}, reason=fields.reason)
    return company(db, company_id)
