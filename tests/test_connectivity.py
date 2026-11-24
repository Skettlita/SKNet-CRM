import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from secrets import token_urlsafe

from fastapi.testclient import TestClient

from app.auth.security import digest
from app.connectivity.private import agent, worker
from app.main import app
from test_access import admin_id, login, migrated, request
from test_platform import accepted, authentication, manual_signup


NETWORKS = {"networks": ["192.168.99.0/24"]}
COLLECTOR_ID = "a" * 64
INVENTORY = {"networks": ["172.20.0.0/30"], "ports": [51820]}
SERVER_KEY = base64.b64encode(bytes([1]) * 32).decode()
PEER_KEY = base64.b64encode(bytes([2]) * 32).decode()


def worker_post(client, endpoint, data):
    return accepted(client.post("/api/v1/worker/" + endpoint, json=data))


def step(client, job, endpoint, **data):
    return worker_post(client, "jobs/" + job["job"] + "/" + endpoint, dict(data, lease=job["lease"]))


def devices(client, endpoint, token, data=None):
    return client.request("GET" if data is None else "POST", "/api/v1/collector/" + endpoint, json=data,
                          headers={"Authorization": "Bearer " + token})


def setup_isp(admin, client, name):
    manual_signup(admin, name)
    accepted(login(client, "isp", "isp-" + name))


def test_provisioning_concurrency_capacity_and_automatic_ticket(migrated, admin_id, monkeypatch):
    monkeypatch.setenv("SKNET_CONNECTIVITY_MODE", "simulation")
    monkeypatch.setenv("SKNET_UDP_LAST", "51822")
    with TestClient(app) as admin, TestClient(app) as one, TestClient(app) as two, TestClient(app) as three, TestClient(worker) as worker_api:
        authentication(admin)
        for client, name in ((one, "one"), (two, "two"), (three, "three")):
            setup_isp(admin, client, name)
        with ThreadPoolExecutor(max_workers=4) as executor:
            clients = (one, one, two, three)
            results = list(executor.map(lambda client: accepted(request(client, "POST", "isp/connectivity", NETWORKS)), clients))
        assert results[0]["id"] == results[1]["id"]
        assert len({record["id"] for record in results}) == 3
        allocations = []
        for _ in range(3):
            job = worker_post(worker_api, "claim", {})
            allocations.append(step(worker_api, job, "reserve", inventory=INVENTORY))
        assert {item["docker_subnet"] for item in allocations[:2]} == {"172.20.0.4/30", "172.20.0.8/30"}
        assert {item["wireguard_subnet"] for item in allocations[:2]} == {"10.200.1.0/31", "10.200.1.2/31"}
        assert {item["port"] for item in allocations[:2]} == {51821, 51822}
        assert allocations[2] == {"error": "UDP_POOL"}
        step(worker_api, job, "finish", error="UDP_POOL")
        failed = migrated.execute("""
            SELECT j.company_id,c.id FROM connectivity.provisioning_jobs j
            JOIN connectivity.collectors c ON c.id=j.collector_id WHERE j.status='FAILED'
        """).fetchone()
        first = migrated.execute("SELECT id FROM platform.support_tickets WHERE company_id=%s", (failed[0],)).fetchone()
        accepted(request(admin, "POST", f"admin/connectivity/collectors/{failed[0]}/{failed[1]}/retry"))
        retry = worker_post(worker_api, "claim", {})
        assert step(worker_api, retry, "reserve", inventory=INVENTORY) == {"error": "UDP_POOL"}
        step(worker_api, retry, "finish", error="UDP_POOL")
        assert migrated.execute("SELECT id FROM platform.support_tickets WHERE company_id=%s", (failed[0],)).fetchall() == [first]
        accepted(request(one, "POST", "isp/support/tickets", {
            "subject": "Consulta de prueba", "description": "Solicitud ingresada por la empresa.", "priority": "NORMAL",
        }), 201)
        automatic = accepted(request(admin, "GET", "admin/support/tickets?automatic=true"))["items"]
        assert [ticket["id"] for ticket in automatic] == [str(first[0])]
        assert sum(len(accepted(request(client, "GET", "isp/connectivity"))["networks"]) for client in (one, two, three)) == 3
        assert request(one, "GET", "admin/connectivity/collectors").status_code == 401


def test_collector_authentication_script_probe_and_recovery(migrated, admin_id, monkeypatch):
    monkeypatch.setenv("SKNET_CONNECTIVITY_MODE", "simulation")
    with TestClient(app) as admin, TestClient(app) as isp, TestClient(worker) as worker_api, TestClient(agent) as collector:
        authentication(admin)
        setup_isp(admin, isp, "probe")
        assert request(isp, "POST", "isp/connectivity", {"networks": ["10.200.1.1/32"]}).status_code == 422
        accepted(request(isp, "POST", "isp/connectivity", NETWORKS))
        job = worker_post(worker_api, "claim", {})
        old_lease = job["lease"]
        allocation = step(worker_api, job, "reserve", inventory=INVENTORY)
        migrated.execute("UPDATE connectivity.provisioning_jobs SET lease_expires_at=now()-interval '1 minute'")
        job = worker_post(worker_api, "claim", {})
        assert job["lease"] != old_lease
        assert step(worker_api, job, "reserve", inventory=INVENTORY)["port"] == allocation["port"]
        assert worker_api.post("/api/v1/worker/jobs/" + job["job"] + "/finish", json={"lease": old_lease}).status_code == 409
        token = token_urlsafe(32)
        step(worker_api, job, "material", public_key=SERVER_KEY, token_hash=digest(token))
        assert devices(collector, "config", token_urlsafe(32)).status_code == 401
        assert request(isp, "GET", "collector/config").status_code == 404
        config = accepted(devices(collector, "config", token))
        assert (config["local_ip"], config["remote_ip"], config["heartbeat"], config["simulated"]) == (
            "10.200.1.0/31", "10.200.1.1", 10, True,
        )
        assert request(isp, "GET", "isp/connectivity/script?preview=true").status_code == 409
        accepted(devices(collector, "heartbeat", token, {"revision": config["revision"]}))
        step(worker_api, job, "finish", container_id=COLLECTOR_ID)
        assert request(isp, "GET", "isp/connectivity/script").status_code == 409
        template = accepted(request(isp, "GET", "isp/connectivity/script?preview=true"))["script"]
        assert template.startswith("# SIMULACIÓN") and SERVER_KEY in template and "51821" in template
        assert request(isp, "PUT", "isp/connectivity/peer", NETWORKS | {"public_key": "invalid"}).status_code == 422
        accepted(request(isp, "PUT", "isp/connectivity/peer", NETWORKS | {"public_key": PEER_KEY}))
        job = worker_post(worker_api, "claim", {})
        config = accepted(devices(collector, "config", token))
        assert config["public_key"] == PEER_KEY
        accepted(devices(collector, "heartbeat", token, {"revision": config["revision"]}))
        step(worker_api, job, "finish", container_id=COLLECTOR_ID)
        view = lambda: accepted(request(isp, "GET", "isp/connectivity"))
        assert view()["connection_status"] == "UNKNOWN"
        now = int(datetime.now(timezone.utc).timestamp())
        accepted(devices(collector, "connectivity", token, {"revision": config["revision"], "handshake": now,
                                                            "ping_ok": True, "diagnostic": "OK"}))
        assert view()["connection_status"] == "CONNECTED" and not view()["connected"]
        for _ in range(3):
            accepted(devices(collector, "connectivity", token, {"revision": config["revision"], "diagnostic": "NO_REPLY"}))
        assert view()["connection_status"] == "DISCONNECTED" and view()["ticket_id"] is None
        target = view()
        endpoint = f"admin/connectivity/collectors/{target['company_id']}/{target['id']}"
        accepted(request(admin, "POST", endpoint + "/rotate"))
        job = worker_post(worker_api, "claim", {})
        new_token = token_urlsafe(32)
        step(worker_api, job, "material", public_key=SERVER_KEY, token_hash=digest(new_token))
        assert devices(collector, "config", token).status_code == 401
        accepted(devices(collector, "heartbeat", new_token, {"revision": config["revision"]}))
        step(worker_api, job, "finish", container_id=COLLECTOR_ID)
        migrated.execute("UPDATE connectivity.collectors SET last_heartbeat_at=now()-interval '31 seconds'")
        worker_post(worker_api, "observations", {"items": [{"id": target["id"], "state": "EXITED"}], "inventory": INVENTORY})
        assert view()["job_status"] == "PENDING" and view()["ticket_id"] and not view()["simulation_preview"]
        job = worker_post(worker_api, "claim", {})
        assert job["operation"] == "RECONCILE"
        accepted(devices(collector, "heartbeat", new_token, {"revision": config["revision"]}))
        step(worker_api, job, "finish", container_id=COLLECTOR_ID)
        accepted(request(admin, "POST", endpoint + "/disable"))
        assert devices(collector, "config", new_token).status_code == 401
        job = worker_post(worker_api, "claim", {})
        step(worker_api, job, "finish")
        assert view()["provisioning_status"] == "DISABLED"
        assert migrated.execute("SELECT status FROM connectivity.resource_allocations").fetchone() == ("ACTIVE",)
        accepted(request(admin, "POST", endpoint + "/remove"))
        job = worker_post(worker_api, "claim", {})
        step(worker_api, job, "finish", error="RETIRE_FAILED")
        assert migrated.execute("SELECT released_at FROM connectivity.resource_allocations").fetchone() == (None,)
        accepted(request(admin, "POST", endpoint + "/retry"))
        job = worker_post(worker_api, "claim", {})
        assert job["operation"] == "REMOVE"
        step(worker_api, job, "finish")
        assert view() is None
        assert migrated.execute("SELECT status FROM connectivity.resource_allocations").fetchone() == ("RELEASED",)


def test_connectivity_plan_and_permission_rollback(migrated, admin_id, monkeypatch):
    monkeypatch.setenv("SKNET_CONNECTIVITY_MODE", "simulation")
    with TestClient(app) as admin, TestClient(app) as isp:
        authentication(admin)
        setup_isp(admin, isp, "limited")
        target = accepted(request(isp, "GET", "isp/me"))
        migrated.execute("""
            DELETE FROM core.role_permissions WHERE company_id=(SELECT id FROM core.companies WHERE name='Empresa limited')
              AND permission_id=(SELECT id FROM core.permissions WHERE code='connectivity.write')
        """)
        assert "connectivity.read" in target["permissions"]
        assert request(isp, "POST", "isp/connectivity", NETWORKS).status_code == 403
        migrated.execute("""
            DELETE FROM platform.plan_features WHERE feature_id=(SELECT id FROM platform.features WHERE code='CONNECTIVITY')
        """)
        assert request(isp, "GET", "isp/connectivity").status_code == 403
        assert migrated.execute("SELECT count(*) FROM connectivity.collectors").fetchone() == (0,)
