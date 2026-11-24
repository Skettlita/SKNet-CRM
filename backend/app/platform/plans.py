from fastapi import HTTPException

from app.auth.store import audit, execute, row, rows


FIELDS = """
    v.description, v.monthly_price AS price, v.currency, v.billing_period, v.trial_days AS duration_days,
    v.max_clients, v.max_users, v.max_devices, v.min_poll_interval_seconds, v.retention_days,
    v.id AS version_id, v.version, v.effective_at
"""
WITH_FEATURES = """
    ARRAY(SELECT f.code FROM platform.plan_features pf JOIN platform.features f ON f.id = pf.feature_id
          WHERE pf.plan_version_id = v.id ORDER BY f.code) AS features
"""


def features(db):
    return rows(db, "SELECT code, name, implemented FROM platform.features ORDER BY name")


def versions(db, plan_id):
    return rows(db, f"""
        SELECT {FIELDS}, {WITH_FEATURES}
        FROM platform.plan_versions v WHERE v.plan_id = :id ORDER BY v.version DESC
    """, id=plan_id)


def plan(db, plan_id):
    record = row(db, """
        SELECT p.id, p.code, p.name, p.active, p.created_at,
               EXISTS (SELECT 1 FROM platform.settings s
                       JOIN platform.plan_versions v ON v.id = s.default_plan_version_id
                       WHERE v.plan_id = p.id) AS is_default
        FROM platform.plans p WHERE p.id = :id
    """, id=plan_id)
    if record is None:
        raise HTTPException(404, "Plan SaaS no encontrado.")
    return {**record, "versions": versions(db, plan_id)}


def list_plans(db, search, active, offset, limit):
    return rows(db, f"""
        SELECT p.id, p.code, p.name, p.active, {FIELDS},
               EXISTS (SELECT 1 FROM platform.plan_versions dv
                       WHERE dv.id=s.default_plan_version_id AND dv.plan_id=p.id) AS is_default, {WITH_FEATURES}
        FROM platform.plans p
        JOIN LATERAL (SELECT x.* FROM platform.plan_versions x WHERE x.plan_id = p.id
                      ORDER BY x.version DESC LIMIT 1) v ON true
        CROSS JOIN platform.settings s
        WHERE (CAST(:active AS boolean) IS NULL OR p.active = :active)
          AND strpos(lower(p.code || ' ' || p.name), lower(:search)) > 0
        ORDER BY lower(p.name), p.id OFFSET :offset LIMIT :limit
    """, search=search or " ", active=active, offset=offset, limit=limit)


def choices(db):
    return rows(db, """
        SELECT p.id, p.code, p.name, v.id AS version_id, v.version,
               v.trial_days AS duration_days, (v.version = max(v.version) OVER (PARTITION BY p.id)) AS latest
        FROM platform.plans p JOIN platform.plan_versions v ON v.plan_id = p.id
        WHERE p.active
        ORDER BY lower(p.name), v.version DESC
    """)


def selected_version(db, version_id, *, active_only=True):
    result = row(db, f"""
        SELECT p.id, p.code, p.name, p.active, {FIELDS}, {WITH_FEATURES}
        FROM platform.plan_versions v JOIN platform.plans p ON p.id = v.plan_id WHERE v.id = :id
    """, id=version_id)
    if result is None or active_only and not result["active"]:
        raise HTTPException(422, "Selecciona una versión de un plan habilitado.")
    return result


def insert_version(db, plan_id, terms, codes):
    version_id = execute(db, """
        INSERT INTO platform.plan_versions(plan_id,version,description,monthly_price,currency,
            billing_period,trial_days,max_clients,max_users,max_devices,min_poll_interval_seconds,retention_days)
        VALUES (:plan, (SELECT COALESCE(max(version),0)+1 FROM platform.plan_versions WHERE plan_id = :plan),
            :description,:price,:currency,:billing_period,:duration_days,:max_clients,:max_users,:max_devices,
            :min_poll_interval_seconds,:retention_days)
        RETURNING id
    """, plan=plan_id, **terms).scalar_one()
    execute(db, """
        INSERT INTO platform.plan_features(plan_version_id,feature_id)
        SELECT :version,id FROM platform.features WHERE code = ANY(:codes)
    """, version=version_id, codes=sorted(codes))
    return version_id


def save(db, actor, data, plan_id=None):
    prior = plan(db, plan_id) if plan_id else None
    previous = prior["versions"][0] if prior else None
    requested = set(data.features)
    implemented = {entry["code"] for entry in features(db) if entry["implemented"]}
    historical = (set(previous["features"]) - implemented) if previous else set()
    if requested - implemented - historical:
        raise HTTPException(422, "Solo se pueden habilitar funcionalidades implementadas.")
    codes = (requested & implemented) | historical
    terms = data.model_dump(exclude={"code", "name", "features"})

    if prior:
        execute(db, "UPDATE platform.plans SET name = :name WHERE id = :id", name=data.name, id=plan_id)
    else:
        if row(db, "SELECT id FROM platform.plans WHERE code=:code", code=data.code) is not None:
            raise HTTPException(409, "Ya existe un plan con ese código.")
        plan_id = execute(db, "INSERT INTO platform.plans(code,name) VALUES (:code,:name) RETURNING id",
                          code=data.code, name=data.name).scalar_one()

    changed = not previous or codes != set(previous["features"]) or any(
        previous[key] != value for key, value in terms.items()
    )
    version = insert_version(db, plan_id, terms, codes) if changed else previous["version_id"]
    audit(db, "plan.update" if prior else "plan.create", "plan", plan_id, actor=actor.id,
          before={"name": prior["name"], "version": dict(previous)} if prior else None,
          after={"name": data.name, "version": dict(selected_version(db, version, active_only=False))})
    return plan(db, plan_id)


def set_active(db, actor, plan_id, active):
    current = plan(db, plan_id)
    if not active and current["is_default"]:
        raise HTTPException(409, "Selecciona otro plan predeterminado antes de desactivar este.")
    if active != current["active"]:
        execute(db, "UPDATE platform.plans SET active = :active WHERE id = :id", active=active, id=plan_id)
        audit(db, "plan.status", "plan", plan_id, actor=actor.id,
              before={"active": current["active"]}, after={"active": active})
    return plan(db, plan_id)
