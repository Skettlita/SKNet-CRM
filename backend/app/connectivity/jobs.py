import ipaddress
from uuid import uuid4

from fastapi import HTTPException

from app.auth.store import execute, row, rows
from app.connectivity.service import collector, configuration, enqueue, event, incident


RETIRE = {"DISABLE", "REMOVE"}


def claim(db):
    settings = configuration(required=True)
    job = row(db, """
        SELECT * FROM connectivity.provisioning_jobs
        WHERE status='PENDING' OR (status='RUNNING' AND coalesce(lease_expires_at,created_at) < now())
        ORDER BY created_at,id LIMIT 1 FOR UPDATE
    """)
    if not job:
        return None
    target = collector(db, job["company_id"], job["collector_id"])
    if job["attempts"] >= 3:
        finish(db, job, target, "LEASE_EXPIRED")
        return None
    lease = uuid4()
    execute(db, """
        UPDATE connectivity.provisioning_jobs SET status='RUNNING',attempts=attempts+1,
            started_at=coalesce(started_at,now()),lease_id=:lease,lease_expires_at=now()+interval '120 seconds'
        WHERE id=:id
    """, id=job["id"], lease=lease)
    execute(db, """
        UPDATE connectivity.collectors SET provisioning_status=CASE WHEN enabled THEN 'PROVISIONING' ELSE 'DISABLED' END,
          provisioning_step=:step WHERE id=:id
    """, id=target["id"], step="RETIRING" if job["operation"] in RETIRE else "RESERVING")
    parameters = resource_info(target, settings)
    return dict(parameters, job=job["id"], operation=job["operation"], lease=lease, mode=settings.mode,
                revision=target["config_revision"], simulated=target["simulated"],
                first_port=settings.port_start, last_port=settings.port_end,
                current_image=target["current_image"], previous_image=job["previous_image"],
                desired_image=job["desired_image"], rollback_started=job["rollback_started"])


def resource_info(target, settings):
    return {
        "id": target["id"], "name": target["name"], "company": target["company_id"],
        "installation": settings.installation, "network_name": target["docker_network_name"],
        "docker_subnet": str(target["docker_subnet"]) if target["docker_subnet"] else None,
        "wireguard_subnet": str(target["wireguard_subnet"]) if target["wireguard_subnet"] else None,
        "port": target["external_udp_port"], "tag": target["edge_rule_tag"],
        "bind": str(target["bind_address"] or settings.bind_ip), "internal_port": target["internal_udp_port"] or settings.internal_port,
        "heartbeat_fresh": target["heartbeat_fresh"], "container_id": target["docker_container_id"],
    }


def active(db, job_id, lease):
    job = row(db, """
        UPDATE connectivity.provisioning_jobs SET lease_expires_at=now()+interval '120 seconds'
        WHERE id=:id AND status='RUNNING' AND lease_id=:lease AND lease_expires_at>now() RETURNING *
    """, id=job_id, lease=lease)
    if not job:
        raise HTTPException(409, "Concesión del trabajo vencida.")
    return job, collector(db, job["company_id"], job["collector_id"])


def free_ranges(pool, prefix, blocked):
    first = int(pool.network_address)
    step = 1 << (32 - prefix)
    limit = int(pool.broadcast_address)
    intervals = sorted((int(net.network_address), int(net.broadcast_address)) for net in blocked if pool.overlaps(net))
    for low, high in intervals:
        if first + step - 1 < low and first <= limit:
            yield range(first, min(limit + 1, (low // step) * step), step)
        if first <= high:
            first = ((high // step) + 1) * step
    if first <= limit:
        yield range(first, limit + 1, step)


def available_network(pool, prefix, blocked):
    addresses = next(free_ranges(pool, prefix, blocked), None)
    return ipaddress.IPv4Network((addresses.start, prefix)) if addresses else None


def registered_pool(db, settings):
    pool = row(db, """
        INSERT INTO connectivity.network_pools(name,docker_pool,wireguard_pool,port_start,port_end,endpoint_host)
        VALUES (:name,CAST(:docker AS cidr),CAST(:wg AS cidr),:start,:end,:endpoint)
        ON CONFLICT(name) DO UPDATE SET docker_pool=EXCLUDED.docker_pool,wireguard_pool=EXCLUDED.wireguard_pool,
            port_start=EXCLUDED.port_start,port_end=EXCLUDED.port_end,endpoint_host=EXCLUDED.endpoint_host
        WHERE NOT EXISTS (SELECT 1 FROM connectivity.resource_allocations
                          WHERE pool_id=connectivity.network_pools.id AND released_at IS NULL)
        RETURNING *
    """, name=settings.installation, docker=str(settings.docker_pool), wg=str(settings.wg_pool),
        start=settings.port_start, end=settings.port_end, endpoint=settings.endpoint)
    if pool is None:
        pool = row(db, "SELECT * FROM connectivity.network_pools WHERE name=:name", name=settings.installation)
    return pool


def reserve(db, target, inventory):
    settings = configuration(required=True)
    if target["simulated"] != settings.simulated:
        return {"error": "CONFIGURATION"}
    if any(net.overlaps(existing) for net in target["desired_routes"] for existing in inventory.networks):
        return {"error": "ROUTE_CONFLICT"}
    if target["allocation_id"]:
        return resource_info(target, settings)
    pool = registered_pool(db, settings)
    if not pool["enabled"] or any(pool[key] != value for key, value in (
        ("docker_pool", settings.docker_pool), ("wireguard_pool", settings.wg_pool),
        ("port_start", settings.port_start), ("port_end", settings.port_end), ("endpoint_host", settings.endpoint),
    )):
        return {"error": "CONFIGURATION"}
    allocations = rows(db, """
        SELECT docker_subnet,wireguard_subnet,external_udp_port FROM connectivity.resource_allocations WHERE released_at IS NULL
    """)
    blocked = [*inventory.networks, *settings.base_networks, *target["desired_routes"]]
    for item in allocations:
        blocked.extend((item["docker_subnet"], item["wireguard_subnet"]))
    docker_net = available_network(settings.docker_pool, 30, blocked)
    wg_net = available_network(settings.wg_pool, 31, blocked)
    taken = set(inventory.ports) | {item["external_udp_port"] for item in allocations}
    port = next((port for port in range(settings.port_start, settings.port_end + 1) if port not in taken), None)
    for resource, code in ((docker_net, "DOCKER_POOL"), (wg_net, "WG_POOL"), (port, "UDP_POOL")):
        if resource is None:
            return {"error": code}
    execute(db, """
        INSERT INTO connectivity.resource_allocations(company_id,collector_id,pool_id,docker_network_name,docker_subnet,
                                                       wireguard_subnet,external_udp_port,edge_rule_tag,bind_address)
        VALUES (:company,:id,:pool,:network,CAST(:docker AS cidr),CAST(:wg AS cidr),:port,:tag,CAST(:bind AS inet))
    """, id=target["id"], company=target["company_id"], pool=pool["id"], docker=str(docker_net),
        wg=str(wg_net), port=port, network=target["name"] + "-net", tag="SKNet:" + target["name"], bind=settings.bind_ip)
    return resource_info(collector(db, target["company_id"]), settings)


def material(db, job, target, data):
    settings = configuration(required=True)
    if not target["allocation_id"] or (target["server_public_key"] and target["server_public_key"] != data.public_key):
        raise HTTPException(409, "El material almacenado no corresponde al túnel.")
    execute(db, """
        INSERT INTO connectivity.vpn_tunnels(company_id,collector_id,allocation_id,server_public_key,private_key_ref,
                                              endpoint_host,internal_udp_port,keepalive_seconds,mtu)
        VALUES (:company,:id,:allocation,:key,:ref,:endpoint,:port,:keepalive,:mtu)
        ON CONFLICT(allocation_id) DO NOTHING
    """, company=target["company_id"], id=target["id"], allocation=target["allocation_id"], key=data.public_key,
        ref=f"collector:{target['id']}", endpoint=settings.endpoint, port=settings.internal_port,
        keepalive=settings.keepalive, mtu=settings.mtu)
    prior = row(db, "SELECT collector_id,revoked_at FROM connectivity.collector_credentials WHERE token_hash=:token",
                token=data.token_hash)
    if prior and (prior["collector_id"] != target["id"] or prior["revoked_at"]):
        raise HTTPException(409, "Credencial inválida para este collector.")
    if not prior:
        if job["operation"] != "ROTATE_KEY" and row(db, """
            SELECT id FROM connectivity.collector_credentials WHERE collector_id=:id AND revoked_at IS NULL
        """, id=target["id"]):
            raise HTTPException(409, "La credencial persistida no coincide.")
        execute(db, """
            UPDATE connectivity.collector_credentials SET revoked_at=now() WHERE collector_id=:id AND revoked_at IS NULL
        """, id=target["id"])
        execute(db, """
            INSERT INTO connectivity.collector_credentials(company_id,collector_id,token_hash) VALUES (:company,:id,:token)
        """, company=target["company_id"], id=target["id"], token=data.token_hash)
        execute(db, "UPDATE connectivity.collectors SET last_heartbeat_at=NULL,applied_revision=NULL WHERE id=:id",
                id=target["id"])


def finish(db, job, target, error=None, container_id=None, *, image=None, rolled_back=False):
    if job["operation"] == "UPGRADE" and (not error or rolled_back):
        expected = job["previous_image"] if rolled_back else job["desired_image"]
        if (image != expected or rolled_back != job["rollback_started"] or (rolled_back and error != "UPGRADE_FAILED")
                or not job["verify_after"] or not target["last_heartbeat_at"]
                or target["last_heartbeat_at"] <= job["verify_after"]):
            raise HTTPException(409, "La imagen verificada no coincide con la operación.")
    elif rolled_back:
        raise HTTPException(409, "La reversión solo está disponible para actualizaciones.")
    if error and not rolled_back:
        incident(db, job["company_id"], target["id"], error)
        execute(db, """
            UPDATE connectivity.collectors SET provisioning_status='ERROR',provisioning_step='FAILED',
                last_error=:error,diagnostic=:error WHERE id=:id
        """, id=target["id"], error=error)
        event(db, target, "ERROR", error)
    elif job["operation"] in RETIRE:
        event(db, target, "DISABLED", "Infraestructura deshabilitada.")
        if job["operation"] == "REMOVE":
            execute(db, "UPDATE connectivity.vpn_tunnels SET retired_at=now(),enabled=false WHERE id=:id", id=target["tunnel_id"])
            execute(db, """
                UPDATE connectivity.resource_allocations SET status='RELEASED',released_at=now() WHERE id=:id
            """, id=target["allocation_id"])
        execute(db, """
            UPDATE connectivity.collectors SET provisioning_status='DISABLED',provisioning_step='COMPLETE',
                retired_at=CASE WHEN :removed THEN now() ELSE retired_at END,
                container_state=:state,last_error=NULL WHERE id=:id
        """, id=target["id"], removed=job["operation"] == "REMOVE",
            state="MISSING" if job["operation"] == "REMOVE" else "EXITED")
        execute(db, "UPDATE connectivity.vpn_tunnels SET connection_status='UNKNOWN' WHERE id=:id", id=target["tunnel_id"])
    else:
        if not (container_id and target["heartbeat_fresh"] and target["tunnel_id"]
                and target["applied_revision"] == target["config_revision"]):
            raise HTTPException(409, "Falta la verificación operativa del collector.")
        execute(db, """
            UPDATE connectivity.resource_allocations SET status='ACTIVE' WHERE id=:id
        """, id=target["allocation_id"])
        execute(db, """
            UPDATE connectivity.collectors SET docker_container_id=:container,provisioning_status=:status,
              provisioning_step='COMPLETE',container_state='RUNNING',last_error=NULL,diagnostic=NULL,
              current_image=coalesce(:image,current_image),observed_image=coalesce(:image,observed_image) WHERE id=:id
        """, id=target["id"], container=container_id, image=image,
            status="WAITING_HANDSHAKE" if target["peer_public_key"] else "WAITING_PUBLIC_KEY")
        if job["operation"] == "UPGRADE":
            event(db, target, "ERROR" if rolled_back else "CONFIG_CHANGED",
                  "Imagen anterior restaurada y verificada." if rolled_back else "Imagen nueva verificada.")
    execute(db, """
        UPDATE connectivity.provisioning_jobs SET status=:status,last_error=:error,error_code=:error,rolled_back=:rollback,
            finished_at=now(),lease_id=NULL,lease_expires_at=NULL WHERE id=:id
    """, id=job["id"], status="FAILED" if error else "SUCCEEDED", error=error, rollback=rolled_back)


def observations(db, items):
    settings = configuration(required=True)
    for item in items:
        owner = row(db, "SELECT company_id FROM connectivity.collectors WHERE id=:id AND retired_at IS NULL", id=item.id)
        if not owner:
            continue
        target = collector(db, owner["company_id"], item.id)
        execute(db, """
            UPDATE connectivity.collectors SET container_state=:state,observed_image=:image,available_image=:available,
              current_image=CASE WHEN :state='RUNNING' AND docker_container_id IS NOT NULL
                                 THEN coalesce(current_image,:image) ELSE current_image END WHERE id=:id
        """, state=item.state, image=item.image, available=item.available_image, id=item.id)
        if (not target["enabled"] or target["simulated"] != settings.simulated
                or target["job_status"] in {"PENDING", "RUNNING"} or not target["last_heartbeat_at"]
                or (target["heartbeat_fresh"] and not item.error and item.state not in {"MISSING", "EXITED"})):
            continue
        if target["provisioning_status"] not in {"WAITING_PUBLIC_KEY", "WAITING_HANDSHAKE", "READY"}:
            continue
        reason = item.error or ("DOCKER_FAILED" if item.state in {"MISSING", "EXITED"} else "COLLECTOR_STALE")
        incident(db, target["company_id"], item.id, reason)
        event(db, target, "ERROR", reason)
        execute(db, """
            UPDATE connectivity.collectors SET provisioning_status='ERROR',diagnostic=:reason,
              provisioning_step='QUEUED' WHERE id=:id
        """, id=item.id, reason=reason)
        execute(db, """
            UPDATE connectivity.vpn_tunnels SET connection_status='UNKNOWN' WHERE id=:id
        """, id=target["tunnel_id"])
        recent = row(db, """
            SELECT id FROM connectivity.provisioning_jobs WHERE collector_id=:id AND operation='RECONCILE'
              AND created_at>now()-interval '15 minutes' LIMIT 1
        """, id=item.id)
        if not recent:
            enqueue(db, target["company_id"], item.id, "RECONCILE")


def residual_resources(db, resources):
    known = {(item["id"], item["company_id"]): item for item in rows(db, """
        SELECT c.id,c.company_id,c.name,c.retired_at,a.docker_network_name
        FROM connectivity.collectors c LEFT JOIN connectivity.resource_allocations a
          ON a.company_id=c.company_id AND a.collector_id=c.id AND a.released_at IS NULL
    """)}
    residual = []
    for resource in resources:
        target = known.get((resource.id, resource.company))
        status = "UNREFERENCED"
        if target:
            expected = {"container": target["name"], "network": target["docker_network_name"],
                        "volume": target["name"] + "-data"}[resource.kind]
            if resource.name == expected and target["retired_at"] is None:
                continue
            if resource.kind == "volume" and resource.name == expected and target["retired_at"]:
                status = "RETAINED"
        residual.append({"name": resource.name, "kind": resource.kind, "status": status})
    return residual
