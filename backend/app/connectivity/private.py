from datetime import datetime, timezone
import json
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.auth.routes import database, write_operation
from app.auth.security import digest
from app.auth.store import execute, row, rows
from app.connectivity import jobs, schemas
from app.connectivity.service import collector, configuration, event
from app.main import lifespan
from app import network_monitoring


def private_app():
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    def bad_request(request, error):
        return JSONResponse({"detail": "Datos inválidos."}, status_code=422)

    return app


worker = private_app()
agent = private_app()
worker_path = "/api/v1/worker"
agent_path = "/api/v1/collector"


@worker.post(worker_path + "/claim")
def claim(request: Request):
    with database(request) as db, write_operation(db):
        return jobs.claim(db)


@worker.post(worker_path + "/jobs/{job_id}/reserve")
def reserve(request: Request, job_id: UUID, data: schemas.Reservation):
    with database(request) as db, write_operation(db):
        _, target = jobs.active(db, job_id, data.lease)
        return jobs.reserve(db, target, data.inventory)


@worker.post(worker_path + "/jobs/{job_id}/material")
def material(request: Request, job_id: UUID, data: schemas.Material):
    with database(request) as db, write_operation(db):
        job, target = jobs.active(db, job_id, data.lease)
        jobs.material(db, job, target, data)
        return {}


@worker.post(worker_path + "/jobs/{job_id}/progress")
def progress(request: Request, job_id: UUID, data: schemas.Progress):
    with database(request) as db, write_operation(db):
        job, target = jobs.active(db, job_id, data.lease)
        if data.reset_heartbeat or data.step in {"UPGRADING", "ROLLBACK"}:
            if job["operation"] != "UPGRADE" and not (
                job["operation"] == "RECONCILE" and data.step == "CONTAINER"
            ):
                raise HTTPException(409, "El trabajo no puede reemplazar el contenedor.")
            if data.step == "ROLLBACK":
                execute(db, """
                    UPDATE connectivity.provisioning_jobs SET rollback_started=true,verify_after=NULL WHERE id=:id
                """, id=job_id)
            if data.reset_heartbeat:
                execute(db, "UPDATE connectivity.collectors SET last_heartbeat_at=NULL,applied_revision=NULL WHERE id=:id",
                        id=target["id"])
                execute(db, "UPDATE connectivity.provisioning_jobs SET verify_after=now() WHERE id=:id", id=job_id)
                execute(db, """
                    UPDATE connectivity.vpn_tunnels SET monitor_epoch=monitor_epoch+1,last_probe_at=NULL,
                      connection_status='UNKNOWN',consecutive_failures=0 WHERE id=:id
                """, id=target["tunnel_id"])
        execute(db, "UPDATE connectivity.collectors SET provisioning_step=:step WHERE id=:id",
                step=data.step, id=target["id"])
        return {"heartbeat_fresh": not data.reset_heartbeat and target["heartbeat_fresh"],
                "applied_revision": None if data.reset_heartbeat else target["applied_revision"]}


@worker.post(worker_path + "/jobs/{job_id}/finish")
def finish(request: Request, job_id: UUID, data: schemas.Completion):
    with database(request) as db, write_operation(db):
        job, target = jobs.active(db, job_id, data.lease)
        jobs.finish(db, job, target, data.error, data.container_id, image=data.image, rolled_back=data.rolled_back)
        return {}


@worker.get(worker_path + "/inventory")
def inventory(request: Request):
    with database(request) as db:
        settings = configuration(required=True)
        return rows(db, """
            SELECT c.id,c.name,c.company_id AS company,:installation AS installation,
                   a.edge_rule_tag AS tag,a.external_udp_port AS port,host(a.bind_address) AS bind
            FROM connectivity.collectors c LEFT JOIN connectivity.resource_allocations a
              ON a.collector_id=c.id AND a.status='ACTIVE' AND c.enabled
           WHERE c.retired_at IS NULL AND c.simulated=:sim
        """, sim=settings.simulated, installation=settings.installation)


@worker.post(worker_path + "/observations")
def observe(request: Request, data: schemas.Observations):
    with database(request) as db, write_operation(db):
        settings = configuration()
        jobs.registered_pool(db, settings)
        jobs.observations(db, data.items)
        execute(db, """
            UPDATE connectivity.network_pools SET observed_networks=CAST(:nets AS cidr[]),observed_ports=:ports,observed_at=now(),
              residual_resources=coalesce(CAST(:residual AS jsonb),residual_resources)
            WHERE name=:name
        """, nets=list(map(str, data.inventory.networks)), ports=data.inventory.ports, name=settings.installation,
            residual=json.dumps(jobs.residual_resources(db, data.resources)) if data.resources is not None else None)
        return {}


def authorize(db, request):
    settings = configuration(required=True)
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or not 40 <= len(authorization[7:]) <= 100:
        raise HTTPException(401, "Credencial inválida.")
    owner = row(db, """
        SELECT x.company_id,x.collector_id FROM connectivity.collector_credentials x
        JOIN connectivity.collectors c ON (c.id,c.company_id)=(x.collector_id,x.company_id)
        WHERE x.token_hash=:hash AND x.revoked_at IS NULL AND (x.expires_at IS NULL OR x.expires_at>now())
          AND c.enabled AND c.retired_at IS NULL AND c.simulated=:sim
    """, hash=digest(authorization[7:]), sim=settings.simulated)
    if not owner:
        raise HTTPException(401, "Credencial inválida.")
    return collector(db, owner["company_id"], owner["collector_id"])


@agent.get(agent_path + "/config")
def config(request: Request):
    with database(request) as db:
        target = authorize(db, request)
        if not target["tunnel_id"]:
            raise HTTPException(409, "No hay túnel asignado.")
        network = target["wireguard_subnet"]
        return {
            "revision": target["config_revision"], "local_ip": f"{network[0]}/31",
            "remote_ip": str(network[1]), "port": target["internal_udp_port"], "mtu": target["mtu"],
            "public_key": target["peer_public_key"], "networks": list(map(str, target["desired_routes"])),
            "heartbeat": configuration().heartbeat, "simulated": target["simulated"],
        }


@agent.post(agent_path + "/heartbeat")
def heartbeat(request: Request, data: schemas.Heartbeat):
    with database(request) as db, write_operation(db):
        target = authorize(db, request)
        if target["last_heartbeat_at"] is not None and not target["heartbeat_fresh"] and target["tunnel_id"]:
            execute(db, "UPDATE connectivity.vpn_tunnels SET monitor_epoch=monitor_epoch+1 WHERE id=:id",
                    id=target["tunnel_id"])
        execute(db, """
            UPDATE connectivity.collectors SET last_heartbeat_at=now(),applied_revision=:applied WHERE id=:id
        """, id=target["id"], applied=data.revision if data.revision == target["config_revision"] else None)
        return {}


@agent.post(agent_path + "/connectivity")
@agent.post(agent_path + "/diagnostics")
def report(request: Request, data: schemas.Probe):
    with database(request) as db, write_operation(db):
        target = authorize(db, request)
        if data.revision != target["config_revision"] or not target["tunnel_id"]:
            return {}
        execute(db, "UPDATE connectivity.collectors SET diagnostic=:message WHERE id=:id AND provisioning_status<>'ERROR'",
                id=target["id"], message=data.diagnostic)
        if not target["peer_public_key"] or target["provisioning_status"] not in {"WAITING_HANDSHAKE", "READY"}:
            return {}
        age = datetime.now(timezone.utc).timestamp() - data.handshake
        handshake = datetime.fromtimestamp(data.handshake, timezone.utc) if data.handshake and age >= -5 else None
        connected = data.ping_ok and data.diagnostic in {"OK","NO_HANDSHAKE"} and handshake is not None and target["heartbeat_fresh"]
        state = row(db, """
            UPDATE connectivity.vpn_tunnels SET last_handshake_at=greatest(CAST(:handshake AS timestamptz),last_handshake_at),last_probe_at=now(),
              last_success_at=CASE WHEN :ok THEN now() ELSE last_success_at END,
              monitor_epoch=monitor_epoch+CASE WHEN (NOT :ok AND consecutive_failures=0)
                OR (:ok AND (consecutive_failures>0 OR last_probe_at IS NULL OR
                    last_probe_at<now()-make_interval(secs=>:stale))) THEN 1 ELSE 0 END,
              consecutive_failures=CASE WHEN :ok THEN 0 ELSE consecutive_failures+1 END,
              connection_status=CASE WHEN :ok THEN 'CONNECTED'
                WHEN consecutive_failures>=2 THEN 'DISCONNECTED' ELSE connection_status END
            WHERE id=:id RETURNING connection_status
        """, id=target["tunnel_id"], ok=connected, handshake=handshake, stale=configuration().stale)["connection_status"]
        if state != target["connection_status"]:
            event(db, target, state, data.diagnostic)
        if connected or state == "DISCONNECTED":
            network_monitoring.sync_transport(db, target, "VPN", not connected, data.diagnostic)
        execute(db, """
            UPDATE connectivity.collectors SET provisioning_status=:status WHERE id=:id
        """, id=target["id"], status="READY" if state == "CONNECTED" else "WAITING_HANDSHAKE")
        return {}


@agent.post(agent_path + "/results")
def results(request: Request, data: network_monitoring.Results):
    with database(request) as db, write_operation(db):
        return network_monitoring.ingest(db, authorize(db, request), data)


@agent.get(agent_path + "/targets")
def targets(request: Request):
    with database(request) as db, write_operation(db):
        return network_monitoring.targets(db, authorize(db, request))
