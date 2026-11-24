import ipaddress
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.auth.store import audit, execute, row, rows
from app.connectivity.config import load


ERRORS = {
    "DOCKER_FAILED": "Docker no pudo preparar o verificar el collector.",
    "PORT_CONFLICT": "El puerto publicado no pudo reservarse en el host.",
    "DOCKER_POOL": "No quedan subredes Docker aprobadas.",
    "WG_POOL": "No quedan subredes WireGuard aprobadas.",
    "UDP_POOL": "No quedan puertos UDP aprobados.",
    "ROUTEROS_FAILED": "La regla NAT o el firewall RouterOS no pudo verificarse.",
    "ROUTE_CONFLICT": "Las redes remotas coinciden con una red protegida.",
    "KEY_FAILED": "No se pudo preparar el material criptográfico.",
    "LEASE_EXPIRED": "El worker no completó el trabajo en el tiempo asignado.",
    "COLLECTOR_STALE": "El collector dejó de enviar señales de vida.",
    "CONFIGURATION": "La instalación no tiene una configuración de red compatible.",
    "RETIRE_FAILED": "La infraestructura todavía existe. La reserva se conserva.",
    "UPGRADE_FAILED": "La imagen nueva no pudo ponerse en servicio.",
    "ROLLBACK_FAILED": "No pudo verificarse la recuperación con la imagen anterior.",
}


def configuration(*, required=False):
    try:
        settings = load()
    except (TypeError, ValueError):
        raise HTTPException(503, ERRORS["CONFIGURATION"]) from None
    if required and settings.mode == "disabled":
        raise HTTPException(503, "El aprovisionamiento no está habilitado en esta instalación.")
    return settings


def collector(db, company, collector_id=None):
    return row(db, """
        SELECT c.*,v.id AS tunnel_id,v.peer_public_key,v.connection_status,v.last_handshake_at,v.last_probe_at,
               v.consecutive_failures,
               v.server_public_key,v.endpoint_host,v.internal_udp_port,v.mtu,v.keepalive_seconds,
               a.id AS allocation_id,a.docker_subnet,a.wireguard_subnet,a.external_udp_port,a.docker_network_name,
               a.edge_rule_tag,a.bind_address,
               j.id AS job_id,j.status AS job_status,j.operation AS job_operation,j.error_code,j.rolled_back,
               (c.last_heartbeat_at IS NOT NULL AND
                 c.last_heartbeat_at > now() - make_interval(secs=>:stale)) AS heartbeat_fresh,
               (v.last_probe_at IS NOT NULL AND
                 v.last_probe_at > now() - make_interval(secs=>:stale)) AS probe_fresh,
               ticket.id AS ticket_id
        FROM connectivity.collectors c
        LEFT JOIN connectivity.resource_allocations a ON a.collector_id=c.id AND a.released_at IS NULL
        LEFT JOIN connectivity.vpn_tunnels v ON v.allocation_id=a.id AND v.retired_at IS NULL
        LEFT JOIN LATERAL (
            SELECT id,status,operation,error_code,rolled_back FROM connectivity.provisioning_jobs
            WHERE collector_id=c.id ORDER BY created_at DESC,id DESC LIMIT 1
        ) j ON true
        LEFT JOIN LATERAL (
            SELECT id FROM platform.support_tickets
            WHERE company_id=c.company_id AND starts_with(fault_key, 'connectivity:' || c.id::text || ':')
              AND status IN ('OPEN','ASSIGNED','IN_PROGRESS','RESOLVED')
            ORDER BY opened_at DESC,id DESC LIMIT 1
        ) ticket ON true
        WHERE c.company_id=:company AND c.retired_at IS NULL
          AND (CAST(:id AS uuid) IS NULL OR c.id=:id)
    """, company=company, id=collector_id, stale=configuration().stale)


def public(record):
    if not record:
        return None
    fields = ("id", "company_id", "name", "enabled", "provisioning_status", "provisioning_step", "container_state",
              "last_heartbeat_at", "heartbeat_fresh", "connection_status", "last_handshake_at", "last_probe_at",
              "diagnostic", "simulated", "job_id", "job_status", "job_operation", "error_code", "ticket_id")
    result = {name: record[name] for name in fields}
    result["networks"] = [str(net) for net in record["desired_routes"]]
    result["connected"] = bool(record["connection_status"] == "CONNECTED" and record["heartbeat_fresh"]
                               and record["probe_fresh"] and not record["simulated"])
    result["transport_connected"] = bool(record["connection_status"] == "CONNECTED" and record["heartbeat_fresh"]
                                         and record["probe_fresh"] and record["consecutive_failures"] == 0)
    if result["connection_status"] == "CONNECTED" and not record["probe_fresh"]:
        result["connection_status"] = "UNKNOWN"
    result["script_available"] = script_allowed(record) and not record["simulated"]
    result["simulation_preview"] = script_allowed(record) and record["simulated"]
    result["peer_configured"] = record["peer_public_key"] is not None
    return result


def script_allowed(record):
    settings = configuration()
    return (settings.mode != "disabled" and settings.simulated == record["simulated"]
            and record["enabled"] and record["provisioning_status"] in {"WAITING_PUBLIC_KEY", "WAITING_HANDSHAKE", "READY"}
            and record["heartbeat_fresh"] and record["container_state"] == "RUNNING"
            and (record["job_status"] == "SUCCEEDED" or record["rolled_back"]) and record["tunnel_id"] is not None)


def enqueue(db, company, collector_id, operation, actor=None, *, previous=None, desired=None):
    pending = row(db, """
        SELECT id,operation,status FROM connectivity.provisioning_jobs WHERE collector_id=:collector
          AND status IN ('PENDING','RUNNING') ORDER BY created_at LIMIT 1
    """, collector=collector_id)
    if pending:
        return pending
    return row(db, """
        INSERT INTO connectivity.provisioning_jobs(company_id,collector_id,operation,idempotency_key,
                                                    requested_by_user_id,previous_image,desired_image)
        VALUES (:company,:collector,:operation,:key,:actor,:previous,:desired) RETURNING id, operation, status
    """, company=company, collector=collector_id, operation=operation, key=str(uuid4()), actor=actor,
        previous=previous, desired=desired)


def validate_routes(networks, blocked):
    if any(net.overlaps(existing) for net in networks for existing in blocked):
        raise HTTPException(422, ERRORS["ROUTE_CONFLICT"])


def begin(db, actor, networks):
    settings = configuration(required=True)
    previous = collector(db, actor.company)
    if previous:
        return public(previous)
    validate_routes(networks, (*settings.base_networks, settings.wg_pool, settings.docker_pool))
    collector_id = uuid4()
    execute(db, """
        INSERT INTO connectivity.collectors(id,company_id,name,desired_routes,simulated)
        VALUES (:id,:company,:name,CAST(:routes AS cidr[]),:simulated)
    """, id=collector_id, company=actor.company, name=f"{settings.installation}-c-{collector_id.hex}",
        routes=[str(net) for net in networks], simulated=settings.simulated)
    enqueue(db, actor.company, collector_id, "CREATE", actor.id)
    audit(db, "connectivity.request", "collector", collector_id, company=actor.company,
          actor=actor.id, after={"networks": list(map(str, networks))})
    return public(collector(db, actor.company))


def stage_peer(db, actor, networks, public_key=None):
    settings = configuration(required=True)
    target = collector(db, actor.company)
    if not target or not target["enabled"] or not target["tunnel_id"]:
        raise HTTPException(409, "Primero prepara tu conexión desde el asistente.")
    pool = row(db, "SELECT observed_networks FROM connectivity.network_pools WHERE name=:name", name=settings.installation)
    blocked = (*settings.base_networks, settings.wg_pool, settings.docker_pool, target["docker_subnet"],
               *(pool["observed_networks"] if pool else ()))
    validate_routes(networks, blocked)
    public_key = public_key or target["peer_public_key"]
    if public_key == target["server_public_key"]:
        raise HTTPException(422, "La clave pública del router debe ser distinta de la de SKNet.")
    selected = list(map(str, networks))
    if public_key == target["peer_public_key"] and selected == list(map(str, target["desired_routes"])):
        return public(target)
    if target["job_status"] in {"PENDING", "RUNNING"}:
        raise HTTPException(409, "Espera a que termine el trabajo en curso.")
    if not script_allowed(target):
        raise HTTPException(409, "La infraestructura todavía no está preparada.")
    execute(db, """
        UPDATE connectivity.collectors SET desired_routes=CAST(:routes AS cidr[]),
            config_revision=config_revision+1, provisioning_status='PROVISIONING',provisioning_step='QUEUED'
        WHERE id=:id
    """, routes=selected, id=target["id"])
    execute(db, """
        UPDATE connectivity.vpn_tunnels SET peer_public_key=:key,connection_status='UNKNOWN',monitor_epoch=monitor_epoch+1,
         consecutive_failures=0,last_handshake_at=NULL,last_probe_at=NULL,last_success_at=NULL WHERE id=:id
    """, key=public_key, id=target["tunnel_id"])
    execute(db, "UPDATE connectivity.vpn_routes SET enabled=false WHERE tunnel_id=:id", id=target["tunnel_id"])
    for network in selected:
        execute(db, """
            INSERT INTO connectivity.vpn_routes(company_id,tunnel_id,destination_network)
            VALUES (:company,:id,CAST(:network AS cidr))
            ON CONFLICT(tunnel_id,destination_network) DO UPDATE SET enabled=true
        """, company=actor.company, id=target["tunnel_id"], network=network)
    event(db, target, "CONFIG_CHANGED", "Configuración del peer actualizada.")
    enqueue(db, actor.company, target["id"], "CONFIGURE", actor.id)
    audit(db, "connectivity.peer", "collector", target["id"], company=actor.company, actor=actor.id,
          before={"networks": list(map(str, target["desired_routes"]))},
          after={"networks": selected, "peer_configured": bool(public_key)})
    return public(collector(db, actor.company))


def event(db, target, kind, detail):
    if target["tunnel_id"]:
        execute(db, """
            INSERT INTO connectivity.vpn_events(company_id,tunnel_id,event_type,detail)
            VALUES (:company,:id,:type,:detail)
        """, company=target["company_id"], id=target["tunnel_id"], type=kind, detail=detail)


def incident(db, company, collector_id, code):
    ticket = execute(db, """
        INSERT INTO platform.support_tickets(company_id,origin,fault_key,subject,description,priority)
        VALUES (:company,'SYSTEM',:fault,'Infraestructura de conectividad SKNet',:detail,'HIGH')
        ON CONFLICT (company_id,fault_key) WHERE origin='SYSTEM' AND status IN ('OPEN','ASSIGNED','IN_PROGRESS','RESOLVED')
        DO UPDATE SET description=EXCLUDED.description RETURNING id
    """, company=company, fault=f"connectivity:{collector_id}:{code}", detail=ERRORS[code]).scalar_one()
    execute(db, """
        INSERT INTO platform.support_ticket_history(company_id,ticket_id,actor_type,new_status,reason)
        SELECT :company,:ticket,'SYSTEM','OPEN',:detail
        WHERE NOT EXISTS (SELECT 1 FROM platform.support_ticket_history WHERE ticket_id=:ticket)
    """, company=company, ticket=ticket, detail=ERRORS[code])
    return ticket


def upgrade_available(target):
    return bool(target["enabled"] and target["allocation_id"] and target["container_state"] == "RUNNING"
                and target["heartbeat_fresh"] and target["current_image"]
                and target["observed_image"] == target["current_image"] and target["available_image"]
                and target["available_image"] != target["current_image"])


def enqueue_action(db, target, operation, actor_id, *, isp=False, retry=False, expected_image=None):
    configuration(required=True)
    if not target:
        raise HTTPException(404, "No se encontró la conexión.")
    if target["job_status"] in {"PENDING", "RUNNING"}:
        if operation == target["job_operation"]:
            return public(target)
        raise HTTPException(409, "Hay un trabajo en curso.")
    if retry and target["provisioning_status"] != "ERROR":
        raise HTTPException(409, "Solo se pueden reintentar trabajos fallidos.")
    if retry and target["job_operation"] in {"ROTATE_KEY", "DISABLE", "REMOVE"}:
        if isp:
            raise HTTPException(403, "Este trabajo requiere la intervención de SKNet.")
        operation = target["job_operation"]
    if operation == "RECONCILE" and not target["enabled"]:
        raise HTTPException(409, "El collector está deshabilitado.")
    if operation == "UPGRADE" and not upgrade_available(target):
        raise HTTPException(409, "No hay una actualización disponible para un collector operativo.")
    if operation == "UPGRADE" and expected_image != target["available_image"]:
        raise HTTPException(409, "La imagen disponible cambió. Revisa la versión y confirma de nuevo.")
    if operation == "ROTATE_KEY" and not script_allowed(target) and target["job_status"] != "FAILED":
        raise HTTPException(409, "Prepara la infraestructura antes de rotar la credencial.")
    if operation in {"DISABLE", "REMOVE"}:
        execute(db, "UPDATE connectivity.collectors SET enabled=false,provisioning_status='DISABLED' WHERE id=:id", id=target["id"])
        execute(db, """
            UPDATE connectivity.collector_credentials SET revoked_at=now()
            WHERE collector_id=:id AND revoked_at IS NULL
        """, id=target["id"])
    else:
        execute(db, "UPDATE connectivity.collectors SET provisioning_status='PENDING',provisioning_step='QUEUED' WHERE id=:id",
                id=target["id"])
    images = {"previous": target["current_image"], "desired": target["available_image"]} if operation == "UPGRADE" else {}
    enqueue(db, target["company_id"], target["id"], operation, actor_id, **images)
    audit(db, f"connectivity.{operation.lower()}", "collector", target["id"], company=target["company_id"], actor=actor_id)
    return public(collector(db, target["company_id"]))


SCRIPT_PATH = Path(__file__).with_name("routeros7.rsc")


def make_script(target, *, preview=False):
    if not script_allowed(target) or bool(target["simulated"]) != preview:
        raise HTTPException(409, "El script todavía no está disponible para este modo.")
    subnet = ipaddress.IPv4Network(target["wireguard_subnet"])
    label = "skn-" + target["id"].hex[:10]
    values = {
        "LABEL": label, "MTU": target["mtu"], "CLIENT_IP": f"{subnet[1]}/31",
        "SERVER_IP": f"{subnet[0]}/32", "ENDPOINT": target["endpoint_host"],
        "PORT": target["external_udp_port"], "PUBLIC_KEY": target["server_public_key"],
        "KEEPALIVE": target["keepalive_seconds"],
    }
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    for key, value in values.items():
        script = script.replace(f"@{key}@", str(value))
    return ("# SIMULACIÓN DEV. VISTA PREVIA. NO EJECUTAR.\n" if preview else "") + script
