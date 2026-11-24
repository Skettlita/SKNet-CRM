import ipaddress
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.auth.store import ISP, SAAS, row, rows
from app.connectivity import schemas, service
from app.platform.routes import read, write

isp = APIRouter(prefix=ISP.path + "/connectivity")
admin = APIRouter(prefix=SAAS.path + "/connectivity")


@isp.get("")
def current(request: Request):
    with read(request, "connectivity.read", ISP) as (db, actor):
        return service.public(service.collector(db, actor.company))


@isp.post("")
def begin(request: Request, data: schemas.Routes):
    with write(request, "connectivity.write", ISP) as (db, actor):
        return service.begin(db, actor, data.networks)


@isp.put("/peer")
def peer(request: Request, data: schemas.Peer):
    with write(request, "connectivity.write", ISP) as (db, actor):
        return service.stage_peer(db, actor, data.networks, data.public_key)


@isp.put("/routes")
def routes(request: Request, data: schemas.Routes):
    with write(request, "connectivity.write", ISP) as (db, actor):
        return service.stage_peer(db, actor, data.networks)


@isp.post("/retry")
def retry(request: Request):
    with write(request, "connectivity.write", ISP) as (db, actor):
        return service.enqueue_action(db, service.collector(db, actor.company), "RECONCILE", actor.id, isp=True)


@isp.get("/script")
def script(request: Request, preview: bool = False):
    with read(request, "connectivity.read", ISP) as (db, actor):
        target = service.collector(db, actor.company)
        if not target:
            raise HTTPException(404, "No hay una conexión configurada.")
        return {"script": service.make_script(target, preview=preview)}


@admin.get("/collectors")
def list_collectors(request: Request, offset: int = Query(0, ge=0)):
    with read(request, "connectivity.read") as (db, _):
        companies = rows(db, """
            SELECT c.id,c.company_id,e.name FROM connectivity.collectors c JOIN core.companies e ON e.id=c.company_id
            WHERE c.retired_at IS NULL ORDER BY c.created_at DESC,c.id LIMIT 26 OFFSET :offset
        """, offset=offset)
        result = []
        for item in companies[:25]:
            target = service.collector(db, item["company_id"], item["id"])
            entry = service.public(target)
            entry["company_name"] = item["name"]
            for field in ("docker_subnet", "wireguard_subnet", "external_udp_port"):
                entry[field] = target[field] if field == "external_udp_port" else str(target[field]) if target[field] else None
            entry["docker_ip"] = str(ipaddress.IPv4Network(target["docker_subnet"])[2]) if target["docker_subnet"] else None
            result.append(entry)
        return {"items": result, "has_more": len(companies) > 25}


@admin.get("/jobs")
def list_jobs(request: Request, offset: int = Query(0, ge=0)):
    with read(request, "connectivity.read") as (db, _):
        items = rows(db, """
            SELECT j.id,j.collector_id,j.operation,j.status,j.attempts,j.created_at,j.started_at,j.finished_at,j.error_code,
              c.name AS company_name FROM connectivity.provisioning_jobs j JOIN core.companies c ON c.id=j.company_id
            ORDER BY j.created_at DESC,j.id LIMIT 26 OFFSET :offset
        """, offset=offset)
        return {"items": items[:25], "has_more": len(items) > 25}


@admin.get("/pools")
def pools(request: Request):
    with read(request, "connectivity.read") as (db, _):
        from app.connectivity.jobs import free_ranges

        settings = service.configuration()
        allocations = rows(db, """
            SELECT docker_subnet,wireguard_subnet,external_udp_port,status FROM connectivity.resource_allocations
            WHERE released_at IS NULL
        """)
        registry = rows(db, "SELECT observed_networks,observed_ports FROM connectivity.network_pools WHERE name=:name",
                        name=settings.installation)
        observed = registry[0] if registry else {"observed_networks": [], "observed_ports": []}
        used_networks = [net for item in allocations for net in (item["docker_subnet"], item["wireguard_subnet"])]
        blocked = [*used_networks, *settings.base_networks, *observed["observed_networks"]]
        used_ports = set(observed["observed_ports"]) | {item["external_udp_port"] for item in allocations}
        metrics = [
            {"name": "Subredes Docker /30", "pool": str(settings.docker_pool), "total": settings.docker_pool.num_addresses // 4,
             "available": sum(map(len, free_ranges(settings.docker_pool, 30, blocked)))},
            {"name": "Subredes WireGuard /31", "pool": str(settings.wg_pool), "total": settings.wg_pool.num_addresses // 2,
             "available": sum(map(len, free_ranges(settings.wg_pool, 31, blocked)))},
            {"name": "Puertos UDP", "pool": f"{settings.port_start}–{settings.port_end}",
             "total": settings.port_end-settings.port_start+1,
             "available": sum(port not in used_ports for port in range(settings.port_start, settings.port_end+1))},
        ]
        return {"mode": settings.mode, "items": metrics, "reserved": len(allocations)}


@admin.get("/system")
def system(request: Request):
    with read(request, "system.read") as (db, _):
        settings = service.configuration()
        state = row(db, """
            SELECT
                (SELECT observed_at FROM connectivity.network_pools WHERE name=:name) AS observed_at,
                (SELECT count(*) FROM connectivity.collectors WHERE retired_at IS NULL AND enabled
                    AND provisioning_status='ERROR') AS failures,
                (SELECT count(*) FROM connectivity.provisioning_jobs WHERE status IN ('PENDING','RUNNING')) AS jobs,
                (SELECT count(*) FROM platform.support_tickets WHERE origin='SYSTEM'
                    AND starts_with(fault_key,'connectivity:') AND status IN ('OPEN','ASSIGNED','IN_PROGRESS')) AS tickets
        """, name=settings.installation)
        return {"mode": settings.mode, **state}


@admin.post("/collectors/{company}/{collector_id}/{action}")
def manage(request: Request, company: UUID, collector_id: UUID, action: Literal["retry", "rotate", "disable", "remove"]):
    operations = {"retry": "RECONCILE", "rotate": "ROTATE_KEY", "disable": "DISABLE", "remove": "REMOVE"}
    with write(request, "connectivity.write") as (db, actor):
        return service.enqueue_action(db, service.collector(db, company, collector_id), operations[action], actor.id)
