from fastapi import HTTPException

from app.auth.store import audit, execute, row, rows
from app.platform.plans import selected_version


SUMMARY = """
    s.id, s.company_id, c.name AS company_name, s.status, s.starts_at, s.ends_at,
    s.plan_version_id, p.code AS plan_code, p.name AS plan_name, v.version AS plan_version,
    v.max_clients, v.max_users, v.max_devices, v.min_poll_interval_seconds, v.retention_days,
    v.monthly_price AS price, v.currency, v.billing_period,
    (s.status IN ('TRIAL','ACTIVE','GRACE') AND s.starts_at <= now()
        AND (s.ends_at IS NULL OR s.ends_at > now())) AS current
"""
JOIN = """
    FROM platform.subscriptions s JOIN core.companies c ON c.id = s.company_id
    JOIN platform.plan_versions v ON v.id = s.plan_version_id
    JOIN platform.plans p ON p.id = v.plan_id
"""


def usage(db, company):
    return row(db, """
        SELECT (SELECT count(*) FROM crm.clients WHERE company_id = :id) AS clients,
               (SELECT count(*) FROM core.memberships m JOIN core.users u ON u.id = m.user_id
                   WHERE m.company_id = :id AND m.active AND u.active) AS users,
               (SELECT count(*) FROM crm.devices WHERE company_id = :id AND monitoring_enabled
                   AND retired_at IS NULL) AS monitored_devices
    """, id=company)


def current_for_company(db, company):
    return row(db, f"""
        SELECT {SUMMARY} {JOIN}
        WHERE s.company_id = :id AND s.status <> 'CANCELLED'
    """, id=company)


def list_subscriptions(db, company, status, search, offset, limit):
    return rows(db, f"""
        SELECT {SUMMARY} {JOIN}
        WHERE (CAST(:company AS uuid) IS NULL OR s.company_id = :company)
          AND (CAST(:status AS text) IS NULL OR s.status = :status)
          AND strpos(lower(c.name || ' ' || p.name), lower(:search)) > 0
        ORDER BY s.starts_at DESC, s.id OFFSET :offset LIMIT :limit
    """, company=company, status=status, search=search, offset=offset, limit=limit)


def subscription_detail(db, subscription_id):
    entry = row(db, f"SELECT {SUMMARY} {JOIN} WHERE s.id = :id", id=subscription_id)
    if entry is None:
        raise HTTPException(404, "Suscripción no encontrada.")
    history = rows(db, """
        SELECT h.id, h.previous_status, h.new_status, h.reason, h.changed_at, u.name AS actor,
               h.previous_starts_at, h.previous_ends_at, h.new_starts_at, h.new_ends_at,
               old_plan.code AS previous_plan, old_version.version AS previous_version,
               new_plan.code AS new_plan, new_version.version AS new_version
        FROM platform.subscription_history h
        LEFT JOIN core.users u ON u.id = h.changed_by
        LEFT JOIN platform.plan_versions old_version ON old_version.id = h.previous_plan_version_id
        LEFT JOIN platform.plans old_plan ON old_plan.id = old_version.plan_id
        LEFT JOIN platform.plan_versions new_version ON new_version.id = h.new_plan_version_id
        LEFT JOIN platform.plans new_plan ON new_plan.id = new_version.plan_id
        WHERE h.company_id = :company AND h.subscription_id = :id
        ORDER BY h.changed_at DESC, h.id
    """, company=entry["company_id"], id=subscription_id)
    return {**entry, "usage": usage(db, entry["company_id"]), "history": history}


def record(db, subscription_id, company, actor, previous, new, reason):
    before = previous or {}
    execute(db, """
        INSERT INTO platform.subscription_history(company_id,subscription_id,changed_by,
            previous_status,new_status,previous_plan_version_id,new_plan_version_id,reason,
            previous_starts_at,previous_ends_at,new_starts_at,new_ends_at)
        VALUES (:company,:subscription,:actor,:previous_status,:new_status,:previous_plan,:new_plan,
            :reason,:previous_start,:previous_end,:new_start,:new_end)
    """, company=company, subscription=subscription_id, actor=actor, reason=reason,
        previous_status=before.get("status"), new_status=new["status"],
        previous_plan=before.get("plan_version_id"), new_plan=new["plan_version_id"],
        previous_start=before.get("starts_at"), previous_end=before.get("ends_at"),
        new_start=new["starts_at"], new_end=new["ends_at"])
    keys = ("plan_version_id", "status", "starts_at", "ends_at")
    audit(db, "subscription.update" if previous else "subscription.create", "subscription",
          subscription_id, actor=actor, company=company,
          before={key: previous[key] for key in keys} if previous else None,
          after={key: new[key] for key in keys})


def start_subscription(db, company, version, actor, *, status, starts_at=None, ends_at=None,
                       use_duration=True, reason):
    entry = row(db, """
        INSERT INTO platform.subscriptions(company_id,plan_version_id,status,starts_at,ends_at)
        VALUES (:company,:version,:status,COALESCE(CAST(:start AS timestamptz),now()),
           CASE WHEN :use_duration
              THEN COALESCE(CAST(:start AS timestamptz),now()) + make_interval(days => :days)
              ELSE CAST(:end AS timestamptz) END)
        RETURNING id, status, starts_at, ends_at, plan_version_id
    """, company=company, version=version["version_id"], status=status, start=starts_at, end=ends_at,
        use_duration=use_duration, days=version["duration_days"])
    record(db, entry["id"], company, actor, None, entry, reason)
    return entry


def assign(db, actor, company, data):
    if row(db, "SELECT id FROM core.companies WHERE id = :id FOR UPDATE", id=company) is None:
        raise HTTPException(404, "Empresa no encontrada.")
    if current_for_company(db, company):
        raise HTTPException(409, "La empresa ya tiene una suscripción. Edita la suscripción existente.")
    if data.status == "CANCELLED":
        raise HTTPException(422, "Una suscripción nueva no puede empezar cancelada.")
    version = selected_version(db, data.plan_version_id)
    starts = data.starts_at or execute(db, "SELECT now()").scalar_one()
    if data.ends_at is not None and data.ends_at <= starts:
        raise HTTPException(422, "El vencimiento debe ser posterior al inicio.")
    return start_subscription(
        db, company, version, actor.id, status=data.status, starts_at=starts, ends_at=data.ends_at,
        use_duration="ends_at" not in data.model_fields_set, reason=data.reason,
    )


def change(db, actor, subscription_id, data):
    previous = row(db, f"SELECT {SUMMARY} {JOIN} WHERE s.id = :id FOR UPDATE OF s", id=subscription_id)
    if previous is None:
        raise HTTPException(404, "Suscripción no encontrada.")
    if previous["status"] == "CANCELLED":
        raise HTTPException(409, "La suscripción cancelada solo se puede consultar.")
    changed_plan = data.plan_version_id != previous["plan_version_id"]
    version = selected_version(db, data.plan_version_id, active_only=changed_plan)
    starts_at = data.starts_at if data.starts_at is not None else previous["starts_at"]
    ends_at = data.ends_at if "ends_at" in data.model_fields_set else previous["ends_at"]
    if ends_at is not None and ends_at <= starts_at:
        raise HTTPException(422, "El vencimiento debe ser posterior al inicio.")
    entry = row(db, """
        UPDATE platform.subscriptions SET plan_version_id = :version, status = :status,
            starts_at = :start, ends_at = :end WHERE id = :id
        RETURNING id,status,starts_at,ends_at,plan_version_id
    """, version=version["version_id"], status=data.status, start=starts_at, end=ends_at, id=subscription_id)
    if any(entry[key] != previous[key] for key in ("status", "starts_at", "ends_at", "plan_version_id")):
        record(db, subscription_id, previous["company_id"], actor.id, previous, entry, data.reason)
    return entry
