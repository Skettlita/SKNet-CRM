from datetime import datetime, UTC
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.auth.store import execute, row, rows
from app.crm import schemas, store


MONITORING_QUOTA = """
    AND administrative_active AND retired_at IS NULL AND (monitoring_enabled OR monitoring_requested)
"""
SERVICE_TRANSITIONS = {
    "PENDING": {"ACTIVE", "CANCELLED"},
    "ACTIVE": {"SUSPENDED", "CANCELLED"},
    "SUSPENDED": {"ACTIVE", "CANCELLED"},
    "CANCELLED": set(),
}


def save(db, actor, resource, fields, record_id=None):
    previous = store.owned(db, resource.table, actor.company, record_id) if record_id else None
    data = fields.model_dump()
    entity = resource.entity
    client = data.get("client_id")
    if resource is store.CLIENTS:
        if previous is None:
            store.enforce_limit(db, actor, "max_clients", "clients")
        duplicate = row(db, """
            SELECT id FROM crm.clients WHERE company_id=:company AND client_code=:code
              AND id IS DISTINCT FROM CAST(:id AS uuid)
        """, company=actor.company, code=fields.client_code, id=record_id)
        if duplicate:
            raise HTTPException(409, "El código de cliente ya está en uso.")
    elif resource is store.SITES:
        validate_site(db, actor, fields, previous)
    elif resource is store.SERVICES:
        validate_service(db, actor, fields, data, previous)
    elif resource is store.DEVICES:
        client = validate_device(db, actor, fields, data, previous)

    if record_id is None:
        record_id = store.insert(db, resource.table, actor.company, data)
        if resource is store.SERVICES:
            service_history(db, actor, record_id, None, "PENDING", None)
    else:
        store.update(db, resource.table, actor.company, record_id, data)
    before = {key: previous[key] for key in data} if previous else None
    if before is not None and resource is store.DEVICES:
        before["client_id"] = store.owned(db, "sites", actor.company, previous["site_id"])["client_id"]
    store.change_event(db, actor, entity, record_id, "update" if previous else "create",
                       before, data, client=client)
    return store.details(db, resource, actor.company, record_id)


def validate_site(db, actor, fields, previous):
    if fields.client_id:
        store.owned(db, "clients", actor.company, fields.client_id)
    if previous and fields.client_id != previous["client_id"]:
        used = row(db, """
            SELECT id FROM crm.services WHERE company_id=:company AND site_id=:site LIMIT 1
        """, company=actor.company, site=previous["id"])
        if used:
            raise HTTPException(409, "El sitio tiene servicios asociados. Conserva su cliente.")


def company_today(db, company_id, when=None):
    timezone = execute(db, "SELECT timezone FROM core.companies WHERE id=:id", id=company_id).scalar_one()
    return (when or datetime.now(UTC)).astimezone(ZoneInfo(timezone)).date()


def validate_service(db, actor, fields, data, previous):
    customer = store.owned(db, "clients", actor.company, fields.client_id)
    site = store.owned(db, "sites", actor.company, fields.site_id)
    plan = store.owned(db, "service_plans", actor.company, fields.plan_id)
    if site["client_id"] != fields.client_id:
        raise HTTPException(422, "El sitio debe pertenecer al cliente del servicio.")
    for key, entry in (("client_id", customer), ("site_id", site), ("plan_id", plan)):
        if (not previous or previous[key] != data[key]) and (
            entry["status"] != "ACTIVE" if key == "client_id" else not entry["active"]
        ):
            raise HTTPException(409, "Selecciona un cliente, sitio y plan habilitados para la nueva asociación.")
    if fields.access_router_id:
        router = store.owned(db, "devices", actor.company, fields.access_router_id)
        if (not previous or previous["access_router_id"] != fields.access_router_id) and (
            router["retired_at"] or not router["administrative_active"]
        ):
            raise HTTPException(409, "El router de acceso debe estar habilitado.")
    if previous and previous["site_id"] != fields.site_id and row(db, """
        SELECT id FROM crm.devices WHERE company_id=:company AND service_id=:service LIMIT 1
    """, company=actor.company, service=previous["id"]):
        raise HTTPException(409, "Desvincula los dispositivos antes de cambiar el sitio del servicio.")
    data["monthly_price"] = fields.monthly_price if fields.monthly_price is not None else (
        previous["monthly_price"] if previous else plan["monthly_price"]
    )
    data["currency"] = fields.currency or (previous["currency"] if previous else plan["currency"])
    data["contracted_on"] = fields.contracted_on or (previous["contracted_on"] if previous else company_today(db, actor.company))
    if previous and previous["activated_at"] and data["contracted_on"] and (
        data["contracted_on"] > company_today(db, actor.company, previous["activated_at"])
    ):
        raise HTTPException(422, "La contratación debe ser anterior o igual a la activación.")
    old_ip = str(previous["service_ip"]) if previous and previous["service_ip"] else None
    if old_ip != fields.service_ip:
        data["service_ip_observed_at"] = datetime.now(UTC) if fields.service_ip else None


def validate_device(db, actor, fields, data, previous):
    site = store.owned(db, "sites", actor.company, fields.site_id)
    if (not previous or previous["site_id"] != fields.site_id) and not site["active"]:
        raise HTTPException(409, "Selecciona un sitio habilitado.")
    if fields.service_id:
        service = store.owned(db, "services", actor.company, fields.service_id)
        if service["site_id"] != fields.site_id:
            raise HTTPException(422, "El sitio del dispositivo debe coincidir con el del servicio.")
        if (not previous or previous["service_id"] != fields.service_id) and service["status"] == "CANCELLED":
            raise HTTPException(409, "Selecciona un servicio que no esté cancelado.")
    if previous:
        if previous["retired_at"]:
            raise HTTPException(409, "El dispositivo retirado solo está disponible para consulta.")
        ip_changed = (str(previous["ip_address"]) if previous["ip_address"] else None) != fields.ip_address
        if ip_changed:
            wants_monitoring = previous["monitoring_requested"] or previous["monitoring_enabled"]
            if wants_monitoring and fields.ip_address is None:
                raise HTTPException(409, "Deshabilita la intención de monitoreo antes de retirar la IP.")
            if previous["collector_id"] or wants_monitoring:
                check_ip_conflict(db, actor.company, previous, fields.ip_address, wants_monitoring)
        if ip_changed or any(previous[key] != data[key] for key in ("site_id", "service_id")):
            data["config_revision"] = previous["config_revision"] + 1
    return site["client_id"]


def check_ip_conflict(db, company, device, address, requested):
    if address is None:
        return
    conflict = row(db, """
        SELECT id FROM crm.devices WHERE company_id=:company AND id<>:id
          AND ip_address=CAST(:address AS inet) AND retired_at IS NULL AND (
            (CAST(:collector AS uuid) IS NOT NULL AND collector_id=:collector)
            OR (:requested AND (
                (collector_id IS NULL AND monitoring_requested AND administrative_active)
                OR (CAST(:collector AS uuid) IS NULL AND collector_id IS NOT NULL)
            ))
          ) LIMIT 1
    """, company=company, id=device["id"], address=address, collector=device["collector_id"], requested=requested)
    if conflict:
        raise HTTPException(409, "La IP de gestión ya está reservada en este ámbito de monitoreo.")


def set_active(db, actor, resource, record_id, fields):
    previous = store.owned(db, resource.table, actor.company, record_id)
    if resource is store.CLIENTS:
        if previous["status"] == "CLOSED":
            raise HTTPException(409, "Un cliente cerrado solo está disponible para consulta.")
        changed = {"status": "ACTIVE" if fields.active else "INACTIVE"}
    elif resource is store.DEVICES:
        if previous["retired_at"]:
            raise HTTPException(409, "Un dispositivo retirado no se puede reactivar desde esta fase.")
        changed = {"administrative_active": fields.active}
        if previous["administrative_active"] != fields.active:
            if fields.active and previous["monitoring_requested"]:
                validate_monitoring_request(db, actor, previous)
                saved_profile = profile(db, actor.company, record_id)
                validate_interval(actor, saved_profile["interval_seconds"])
            changed["config_revision"] = previous["config_revision"] + 1
        if not fields.active:
            changed["monitoring_enabled"] = False
    else:
        changed = {"active": fields.active}
    if any(previous[key] != value for key, value in changed.items()):
        store.update(db, resource.table, actor.company, record_id, changed)
        client = previous.get("client_id")
        if resource is store.DEVICES:
            client = store.owned(db, "sites", actor.company, previous["site_id"])["client_id"]
        store.change_event(db, actor, resource.entity, record_id, "status",
                           {key: previous[key] for key in changed}, changed, client=client, reason=fields.reason)
    return store.details(db, resource, actor.company, record_id)


def service_history(db, actor, service_id, previous, status, reason):
    execute(db, """
        INSERT INTO crm.service_status_history(company_id,service_id,changed_by,previous_status,new_status,reason)
        VALUES (:company,:id,:actor,:before,:after,:reason)
    """, company=actor.company, id=service_id, actor=actor.user["person_id"], before=previous, after=status, reason=reason)


def service_status(db, actor, record_id, fields):
    previous = store.owned(db, "services", actor.company, record_id)
    before, after = previous["status"], fields.status
    if after == before:
        return store.details(db, store.SERVICES, actor.company, record_id)
    if after not in SERVICE_TRANSITIONS[before]:
        raise HTTPException(409, "La transición de estado del servicio no está permitida.")
    updates = {"status": after}
    if after == "ACTIVE" and previous["activated_at"] is None:
        when = fields.activated_at or datetime.now(UTC)
        if when > datetime.now(UTC) or previous["contracted_on"] and company_today(db, actor.company, when) < previous["contracted_on"]:
            raise HTTPException(422, "La activación debe estar entre la contratación y el momento actual.")
        updates["activated_at"] = when
    elif fields.activated_at is not None:
        raise HTTPException(422, "La fecha solo se indica en la primera activación.")
    if after == "CANCELLED":
        updates["cancelled_at"] = datetime.now(UTC)
    store.update(db, "services", actor.company, record_id, updates)
    service_history(db, actor, record_id, before, after, fields.reason)
    store.change_event(db, actor, "service", record_id, "status",
                       {key: previous[key] for key in updates}, updates, client=previous["client_id"], reason=fields.reason)
    return store.details(db, store.SERVICES, actor.company, record_id)


def state_history(db, company, record_id, offset, limit):
    store.owned(db, "services", company, record_id)
    data = rows(db, """
        SELECT h.id,h.changed_at,h.previous_status,h.new_status,h.reason,u.name AS actor
        FROM crm.service_status_history h
        LEFT JOIN core.memberships m ON m.company_id=h.company_id AND m.id=h.changed_by
        LEFT JOIN core.users u ON u.id=m.user_id
        WHERE h.company_id=:company AND h.service_id=:id
        ORDER BY h.changed_at DESC,h.id OFFSET :offset LIMIT :limit
    """, company=company, id=record_id, offset=offset, limit=limit + 1)
    return {"items": data[:limit], "has_more": len(data) > limit}


def profile(db, company, device_id):
    device = store.owned(db, "devices", company, device_id)
    existing = row(db, """
        SELECT interval_seconds,timeout_ms,packet_count,latency_warning_ms,loss_warning_pct,loss_failure_pct,
          failure_threshold,recovery_threshold
        FROM monitoring.icmp_profiles WHERE company_id=:company AND device_id=:id
    """, company=company, id=device_id)
    requested = device["monitoring_requested"] or device["monitoring_enabled"]
    if existing:
        return {**existing, "requested": requested, "configured": True}
    return {
        **schemas.IcmpProfile(requested=requested).model_dump(), "configured": False,
    }


def validate_monitoring_request(db, actor, device):
    actor.require("icmp.write")
    if device["ip_address"] is None:
        raise HTTPException(422, "Registra una IP de gestión IPv4 antes de habilitar la configuración.")
    check_ip_conflict(db, actor.company, device, str(device["ip_address"]), True)
    store.enforce_limit(db, actor, "max_devices", "devices", MONITORING_QUOTA)


def validate_interval(actor, interval):
    minimum = actor.plan["min_poll_interval_seconds"]
    if minimum is not None and interval < minimum:
        raise HTTPException(422, f"El plan exige un intervalo mínimo de {minimum} segundos.")


def save_profile(db, actor, device_id, fields):
    device = store.owned(db, "devices", actor.company, device_id)
    if device["retired_at"]:
        raise HTTPException(409, "El dispositivo está retirado.")
    validate_interval(actor, fields.interval_seconds)
    was_requested = device["monitoring_requested"] or device["monitoring_enabled"]
    if fields.requested and (device["ip_address"] is None or not device["administrative_active"]):
        raise HTTPException(422, "El dispositivo debe estar habilitado y tener IP de gestión.")
    if fields.requested and not was_requested:
        validate_monitoring_request(db, actor, device)
    before = profile(db, actor.company, device_id)
    values = fields.model_dump(exclude={"requested"})
    execute(db, """
        INSERT INTO monitoring.icmp_profiles(company_id,device_id,enabled,interval_seconds,timeout_ms,packet_count,
            latency_warning_ms,loss_warning_pct,loss_failure_pct,failure_threshold,recovery_threshold)
        VALUES (:company,:id,:enabled,:interval_seconds,:timeout_ms,:packet_count,
            :latency_warning_ms,:loss_warning_pct,:loss_failure_pct,:failure_threshold,:recovery_threshold)
        ON CONFLICT (device_id) DO UPDATE SET enabled=EXCLUDED.enabled, interval_seconds=EXCLUDED.interval_seconds,
            timeout_ms=EXCLUDED.timeout_ms,packet_count=EXCLUDED.packet_count,latency_warning_ms=EXCLUDED.latency_warning_ms,
            loss_warning_pct=EXCLUDED.loss_warning_pct,loss_failure_pct=EXCLUDED.loss_failure_pct,
            failure_threshold=EXCLUDED.failure_threshold,recovery_threshold=EXCLUDED.recovery_threshold
        WHERE monitoring.icmp_profiles.company_id=EXCLUDED.company_id
    """, company=actor.company, id=device_id, enabled=fields.requested, **values)
    store.update(db, "devices", actor.company, device_id, {
        "monitoring_requested": fields.requested,
        "monitoring_enabled": device["monitoring_enabled"] and fields.requested,
        "config_revision": device["config_revision"] + 1,
    })
    after = profile(db, actor.company, device_id)
    site = store.owned(db, "sites", actor.company, device["site_id"])
    store.change_event(db, actor, "device", device_id, "icmp", before, after, client=site["client_id"])
    return after
