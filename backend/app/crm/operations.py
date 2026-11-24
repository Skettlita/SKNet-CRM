from datetime import datetime, UTC
from ipaddress import ip_address
import json
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.auth.store import execute, row, rows
from app.crm import schemas, store
from app.crm.classification import ACCESS_CAPABILITY
from app.validation import problem


MONITORING_QUOTA = """
    AND administrative_active AND retired_at IS NULL AND (monitoring_enabled OR monitoring_requested)
"""
SERVICE_TRANSITIONS = {
    "PENDING": {"ACTIVE", "CANCELLED"},
    "ACTIVE": {"SUSPENDED", "CANCELLED"},
    "SUSPENDED": {"ACTIVE", "CANCELLED"},
    "CANCELLED": set(),
}


def save(db, actor, resource, fields, record_id=None, *, installation="UNDEFINED"):
    previous = store.owned(db, resource.table, actor.company, record_id) if record_id else None
    if previous and previous["archived_at"]:
        raise HTTPException(409, "El registro archivado está disponible para consulta.")
    data = fields.model_dump(exclude={"initial_status"})
    entity = resource.entity
    client = data.get("client_id")
    if resource is store.CLIENTS:
        if previous is None:
            store.enforce_limit(db, actor, "max_clients", "clients")
    elif resource is store.SITES:
        validate_site(db, actor, fields, data, previous)
        if not previous and fields.client_address_id and data["name"] == store.owned(
            db, "clients", actor.company, fields.client_id
        )["client_code"]:
            existing = row(db, """
                SELECT id FROM crm.sites WHERE company_id=:company AND client_id=:client
                  AND client_address_id=:address AND site_type=:type AND active AND archived_at IS NULL
                ORDER BY created_at,id LIMIT 1
            """, company=actor.company, client=fields.client_id, address=fields.client_address_id, type=fields.site_type)
            if existing:
                return store.details(db, resource, actor.company, existing["id"])
    elif resource is store.SERVICES:
        initial_status = getattr(fields, "initial_status", None)
        if previous and initial_status:
            raise problem("initial_status", "Cambia el estado desde la acción de la ficha del servicio.")
        validate_service(db, actor, fields, data, previous)
        if previous is None:
            data["installation_situation"] = installation
            if (initial_status or ("ACTIVE" if installation == "EXISTING" else "PENDING")) == "ACTIVE":
                actor.require("services.status")
                if data["contracted_on"] > company_today(db, actor.company):
                    raise HTTPException(422, "Un servicio activo no puede tener una fecha de contratación futura.")
                data.update(status="ACTIVE", activated_at=datetime.now(UTC))
    elif resource is store.DEVICES:
        from app.crm.inventory import device_labels

        device_labels(db, actor.company, fields, data, previous)
        client = validate_device(db, actor, fields, data, previous)

    if record_id is None:
        if entity in store.CODE_PREFIX:
            data[f"{entity}_code"] = store.commercial_code(db, actor.company, entity)
        record_id = store.insert(db, resource.table, actor.company, data)
        if resource is store.SERVICES:
            notes = {"NEW": "Requiere instalación", "EXISTING": "Servicio previamente instalado"}
            service_history(db, actor, record_id, None, data.get("status", "PENDING"), notes.get(installation))
    else:
        store.update(db, resource.table, actor.company, record_id, data)
        if resource is store.SERVICES and "service_ip_observed_at" in data:
            revise_service_targets(db, actor.company, record_id, fields.service_ip)
    before = {key: previous[key] for key in data} if previous else None
    if resource is store.DEVICES:
        assignment_history(db, actor, record_id, previous, data)
        if "config_revision" in data:
            close_monitoring_incident(db, actor.company, record_id, "CONFIG_CHANGED")
        if before is not None and previous["site_id"]:
            before["client_id"] = store.owned(db, "sites", actor.company, previous["site_id"])["client_id"]
    store.change_event(db, actor, entity, record_id, "update" if previous else "create",
                       before, data, client=client)
    return store.details(db, resource, actor.company, record_id)


def register_customer(db, actor, fields):
    if fields.service:
        actor.require("sites.create")
        actor.require("services.create")
    profile = schemas.Client.model_validate(fields.model_dump(
        exclude={"address", "service", "site", "installation_situation", "initial_status", "equipment"}
    ))
    client = save(db, actor, store.CLIENTS, profile)
    address_id = None
    if fields.address:
        address = fields.address.model_dump()
        address_id = store.insert(db, store.ADDRESSES, actor.company, {**address, "client_id": client["id"]})
        store.change_event(db, actor, "address", address_id, "create", after=address, client=client["id"])
    site, service, equipment = None, None, None
    if fields.site:
        site_fields = schemas.Site(
            **fields.site.model_dump(exclude={"use_client_address", "name"}),
            name=client["client_code"] if fields.site.use_client_address else fields.site.name, client_id=client["id"],
            client_address_id=address_id if fields.site.use_client_address else None,
        )
        site = save(db, actor, store.SITES, site_fields)
        service_fields = schemas.Service(**fields.service.model_dump(), client_id=client["id"], site_id=site["id"],
                                        initial_status=fields.initial_status)
        service = save(db, actor, store.SERVICES, service_fields, installation=fields.installation_situation)
        if fields.equipment:
            from app.crm.inventory import take_available

            device_id = take_available(db, actor, fields.equipment, category="CUSTOMER_EQUIPMENT")
            equipment = assign_device(db, actor, device_id, schemas.Assignment(
                client_id=client["id"], site_id=site["id"], service_id=service["id"], assignment_state="ASSIGNED",
                ip_mode="NONE", reason="Asignación desde alta de abonado",
            ))
    return {"client": client, "site": site, "service": service, "equipment": equipment, "installation": None}


def validate_site(db, actor, fields, data, previous):
    if fields.client_id:
        linked = store.owned(db, "clients", actor.company, fields.client_id)
        if linked["archived_at"] and (not previous or previous["client_id"] != fields.client_id):
            raise problem("client_id", "Selecciona un cliente sin archivar.", 409)
    if previous and fields.client_id != previous["client_id"]:
        used = row(db, """
            SELECT id FROM crm.services WHERE company_id=:company AND site_id=:site
            UNION ALL SELECT id FROM crm.devices WHERE company_id=:company AND site_id=:site LIMIT 1
        """, company=actor.company, site=previous["id"])
        if used:
            raise HTTPException(409, "El sitio tiene servicios o equipos asociados. Conserva su cliente.")
    if (previous and "client_address_id" not in fields.model_fields_set and fields.client_id == previous["client_id"]
            and not fields.address and not fields.city):
        data["client_address_id"] = previous["client_address_id"]
    if data["client_address_id"]:
        linked = store.owned(db, store.ADDRESSES, actor.company, data["client_address_id"])
        if linked["client_id"] != fields.client_id:
            raise HTTPException(422, "La dirección debe pertenecer al cliente del sitio.")


def company_today(db, company_id, when=None):
    timezone = execute(db, "SELECT timezone FROM core.companies WHERE id=:id", id=company_id).scalar_one()
    return (when or datetime.now(UTC)).astimezone(ZoneInfo(timezone)).date()


def validate_service(db, actor, fields, data, previous):
    customer = store.owned(db, "clients", actor.company, fields.client_id)
    site = store.owned(db, "sites", actor.company, fields.site_id)
    plan = store.owned(db, "service_plans", actor.company, fields.plan_id)
    if site["client_id"] != fields.client_id:
        raise problem("site_id", "El sitio debe pertenecer al cliente del servicio.")
    for key, entry in (("client_id", customer), ("site_id", site), ("plan_id", plan)):
        if (not previous or previous[key] != data[key]) and (
            entry["archived_at"] or (entry["status"] != "ACTIVE" if key == "client_id" else not entry["active"])
        ):
            raise problem(key, "Selecciona un registro habilitado para la nueva asociación.", 409)
    if fields.access_router_id:
        router = store.owned(db, "devices", actor.company, fields.access_router_id)
        if not previous or previous["access_router_id"] != fields.access_router_id or previous["access_method"] != fields.access_method:
            if router["device_category"] != "INFRASTRUCTURE":
                raise problem("access_router_id", "Selecciona un equipo de infraestructura.")
            if router["retired_at"] or router["assignment_state"] != "INSTALLED" or not router["administrative_active"]:
                raise problem("access_router_id", "El router de acceso debe estar instalado y habilitado.", 409)
            router_site = store.owned(db, "sites", actor.company, router["site_id"])
            if not router_site["active"] or router_site["archived_at"]:
                raise problem("access_router_id", "El router de acceso debe estar en un sitio activo.", 409)
            if ACCESS_CAPABILITY[fields.access_method] not in router["capabilities"]:
                raise problem("access_router_id", "Selecciona un router compatible con la modalidad de acceso.")
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


PLACEMENT_KEYS = ("site_id", "service_id", "ip_mode", "ip_address", "assignment_state")


def assignment_history(db, actor, record_id, before, after, reason=None):
    old = {key: before[key] for key in PLACEMENT_KEYS} if before else None
    current = {key: after[key] for key in PLACEMENT_KEYS}
    if (old is None and current["assignment_state"] == "AVAILABLE") or (
        old is not None and all(str(old[key]) == str(current[key]) for key in PLACEMENT_KEYS)
    ):
        return
    execute(db, """
        INSERT INTO crm.device_assignments(company_id,device_id,actor_id,previous_data,current_data,reason)
        VALUES (:company,:id,:actor,CAST(:old AS jsonb),CAST(:current AS jsonb),:reason)
    """, company=actor.company, id=record_id, actor=actor.user["person_id"],
        old=json.dumps(old, default=str) if old else None, current=json.dumps(current, default=str), reason=reason)


def assign_device(db, actor, record_id, fields):
    previous = store.owned(db, "devices", actor.company, record_id)
    if previous["retired_at"] or previous["archived_at"]:
        raise HTTPException(409, "El dispositivo retirado está disponible para consulta.")
    if fields.only_available and (previous["assignment_state"] != "AVAILABLE" or not previous["administrative_active"]
                                  or previous["site_id"] or previous["service_id"]):
        raise problem("device_id", "Esta unidad ya no está disponible en stock.", 409)
    data = fields.model_dump(exclude={"reason", "only_available"})
    if not fields.site_id:
        ensure_access_router(db, actor.company, previous, previous["device_category"], previous["capabilities"], None)
    client = validate_placement(db, actor, fields, data, previous["device_category"], previous)
    store.update(db, "devices", actor.company, record_id, data)
    assignment_history(db, actor, record_id, previous, data, fields.reason)
    if "config_revision" in data:
        close_monitoring_incident(db, actor.company, record_id, "CONFIG_CHANGED")
    store.change_event(db, actor, "device", record_id, "assignment",
                       {key: previous[key] for key in PLACEMENT_KEYS}, data, client=client, reason=fields.reason)
    return store.details(db, store.DEVICES, actor.company, record_id)


def validate_placement(db, actor, fields, data, category, previous):
    site = store.owned(db, "sites", actor.company, fields.site_id) if fields.site_id else None
    service = store.owned(db, "services", actor.company, fields.service_id) if fields.service_id else None
    client = site["client_id"] if site else None
    if fields.client_id is not None:
        store.owned(db, "clients", actor.company, fields.client_id)
        if fields.client_id != client:
            raise problem("site_id", "El sitio debe pertenecer al cliente del dispositivo.")
    data.pop("client_id", None)
    if site and (site["site_category"] == "CUSTOMER") != (category == "CUSTOMER_EQUIPMENT"):
        raise problem("site_id", "La categoría del dispositivo debe coincidir con la del sitio.")
    if site and (not previous or previous["site_id"] != site["id"]):
        if not site["active"] or site["archived_at"]:
            raise problem("site_id", "Selecciona un sitio habilitado.", 409)
        if client and store.owned(db, "clients", actor.company, client)["archived_at"]:
            raise problem("site_id", "Este sitio pertenece a un cliente archivado.", 409)
    if service:
        if category != "CUSTOMER_EQUIPMENT" or service["site_id"] != fields.site_id or service["client_id"] != client:
            raise problem("service_id", "El equipo final, el cliente, el sitio y el servicio deben coincidir.")
        if (not previous or previous["service_id"] != service["id"]) and (service["status"] == "CANCELLED" or service["archived_at"]):
            raise problem("service_id", "Selecciona un servicio vigente.", 409)
    if fields.assignment_state:
        state = fields.assignment_state
    elif previous and fields.site_id == previous["site_id"]:
        state = previous["assignment_state"]
    else:
        state = ("ASSIGNED" if previous else "INSTALLED") if site else "AVAILABLE"
    if (state == "AVAILABLE" and (site or service)) or (state in {"ASSIGNED", "INSTALLED"} and not site):
        raise problem("assignment_state", "El estado debe corresponder con la ubicación asignada.")
    mode = fields.ip_mode or ("INDEPENDENT" if fields.ip_address else "NONE")
    if mode == "SERVICE" and not service:
        raise problem("ip_mode", "Para heredar la IP selecciona un servicio asociado.")
    if (mode == "INDEPENDENT") != bool(fields.ip_address):
        raise problem("ip_address", "Introduce una IPv4 solo para el modo de IP independiente.")
    effective = str(fields.ip_address) if mode == "INDEPENDENT" else (
        str(service["service_ip"]) if mode == "SERVICE" and service["service_ip"]
        and ip_address(service["service_ip"]).version == 4 and service["status"] != "CANCELLED" and not service["archived_at"] else None
    )
    data.update(assignment_state=state, ip_mode=mode)
    if state == "INSTALLED" and (not previous or previous["assignment_state"] != "INSTALLED" or previous["site_id"] != fields.site_id):
        data["installed_at"] = datetime.now(UTC)
    if previous and any(str(previous[key]) != str(data[key]) for key in PLACEMENT_KEYS):
        if not site or state in {"AVAILABLE","MAINTENANCE"}:
            data["monitoring_enabled"] = False
        if previous["monitoring_requested"] or previous["monitoring_enabled"]:
            check_ip_conflict(db, actor.company, previous, effective, True)
        data.update(config_revision=previous["config_revision"] + 1, monitoring_enabled=False)
    return client


def validate_device(db, actor, fields, data, previous):
    site = store.owned(db, "sites", actor.company, fields.site_id) if fields.site_id else None
    category = fields.device_category or (
        ("CUSTOMER_EQUIPMENT" if site["client_id"] else "INFRASTRUCTURE") if site
        else previous["device_category"] if previous else None
    )
    if not category:
        raise problem("device_category", "Selecciona la categoría del equipo.")
    capabilities = fields.capabilities
    if capabilities is None:
        capabilities = previous["capabilities"] if previous and category == "INFRASTRUCTURE" else []
    if category == "CUSTOMER_EQUIPMENT" and capabilities:
        raise problem("capabilities", "Las capacidades de red se asignan a equipos de infraestructura.")
    data.update(device_category=category, capabilities=sorted(capabilities),
                ownership=fields.ownership or (previous["ownership"] if previous else "UNKNOWN"))
    if previous:
        for optional_field in ("serial_number", "mac_address"):
            if optional_field not in fields.model_fields_set:
                data.pop(optional_field)
        if previous["device_category"] != category or not site or set(previous["capabilities"]) - set(capabilities):
            ensure_access_router(db, actor.company, previous, category, capabilities, site)
    return validate_placement(db, actor, fields, data, category, previous)


def ensure_access_router(db, company, previous, category, capabilities, site):
    references = rows(db, """
        SELECT DISTINCT access_method FROM crm.services WHERE company_id=:company AND access_router_id=:id
          AND status<>'CANCELLED' AND archived_at IS NULL
    """, company=company, id=previous["id"])
    if any(category != "INFRASTRUCTURE" or not site or (
        ACCESS_CAPABILITY[item["access_method"]] in previous["capabilities"]
        and ACCESS_CAPABILITY[item["access_method"]] not in capabilities
    ) for item in references):
        raise HTTPException(409, "El equipo proporciona acceso a servicios vigentes. Conserva su asignación y capacidades.")


def check_ip_conflict(db, company, device, address, requested):
    if address is None:
        return
    conflict = row(db, """
        SELECT id FROM crm.device_targets WHERE company_id=:company AND id<>:id
          AND effective_ip=CAST(:address AS inet) AND retired_at IS NULL AND archived_at IS NULL
          AND administrative_active AND (monitoring_enabled OR monitoring_requested) LIMIT 1
    """, company=company, id=device["id"], address=address)
    if conflict:
        raise problem("requested", "La IP de gestión ya está reservada en este ámbito de monitoreo.", 409)


def revise_service_targets(db, company, service_id, value):
    devices = rows(db, """
        SELECT id,monitoring_requested,monitoring_enabled FROM crm.devices
        WHERE company_id=:company AND service_id=:service AND ip_mode='SERVICE' AND retired_at IS NULL
    """, company=company, service=service_id)
    if value and ip_address(value).version == 4:
        for device in devices:
            if device["monitoring_requested"] or device["monitoring_enabled"]:
                check_ip_conflict(db, company, device, value, True)
    for device in devices:
        close_monitoring_incident(db, company, device["id"], "CONFIG_CHANGED")
    execute(db, """
        UPDATE crm.devices SET config_revision=config_revision+1,monitoring_enabled=false
        WHERE company_id=:company AND service_id=:service AND ip_mode='SERVICE' AND retired_at IS NULL
    """, company=company, service=service_id)


def close_monitoring_incident(db, company, device_id, reason):
    execute(db, """
        UPDATE monitoring.incidents SET ended_at=greatest(now(),started_at),end_reason=:reason
        WHERE company_id=:company AND device_id=:id AND ended_at IS NULL
    """, company=company, id=device_id, reason=reason)


def set_active(db, actor, resource, record_id, fields):
    previous = store.owned(db, resource.table, actor.company, record_id)
    if previous["archived_at"]:
        raise HTTPException(409, "El registro archivado está disponible para consulta.")
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
        if resource is store.DEVICES and not fields.active:
            close_monitoring_incident(db, actor.company, record_id, "DISABLED")
        client = previous.get("client_id")
        if resource is store.DEVICES and previous["site_id"]:
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
    if previous["archived_at"]:
        raise HTTPException(409, "El servicio archivado está disponible para consulta.")
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
    if after == "CANCELLED":
        revise_service_targets(db, actor.company, record_id, None)
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
    target = row(db, "SELECT effective_ip FROM crm.device_targets WHERE company_id=:company AND id=:id",
                 company=actor.company, id=device["id"])
    if target["effective_ip"] is None or device["assignment_state"] != "INSTALLED":
        raise problem("requested", "Instala el equipo y configura una IPv4 de gestión antes de solicitar monitoreo.")
    check_ip_conflict(db, actor.company, device, str(target["effective_ip"]), True)
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
    if fields.requested and not device["administrative_active"]:
        raise problem("requested", "El dispositivo debe estar habilitado.")
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
    close_monitoring_incident(db, actor.company, device_id, "CONFIG_CHANGED" if fields.requested else "DISABLED")
    after = profile(db, actor.company, device_id)
    site = store.owned(db, "sites", actor.company, device["site_id"]) if device["site_id"] else None
    store.change_event(db, actor, "device", device_id, "icmp", before, after, client=site["client_id"] if site else None)
    return after
