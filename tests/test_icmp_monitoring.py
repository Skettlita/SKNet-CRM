from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.security import digest
from app.connectivity.private import agent, worker
from app.db import create_database_engine, create_session_factory
from app.main import app
from app.network_monitoring import sweep
from test_access import admin_id, migrated, request
from test_connectivity import INVENTORY, NETWORKS, PEER_KEY, SERVER_KEY, devices, setup_isp, step, worker_post
from test_crm import CRM, make, make_site
from test_platform import accepted, authentication


def establish(isp, worker_api, collector, container):
    accepted(request(isp, "POST", "isp/connectivity", NETWORKS))
    job = worker_post(worker_api, "claim", {})
    step(worker_api, job, "reserve", inventory=INVENTORY)
    token = token_urlsafe(32)
    step(worker_api, job, "material", public_key=SERVER_KEY, token_hash=digest(token))
    config = accepted(devices(collector, "config", token))
    accepted(devices(collector, "heartbeat", token, {"revision": config["revision"]}))
    step(worker_api, job, "finish", container_id=container)
    accepted(request(isp, "PUT", "isp/connectivity/peer", NETWORKS | {"public_key": PEER_KEY}))
    job = worker_post(worker_api, "claim", {})
    config = accepted(devices(collector, "config", token))
    accepted(devices(collector, "heartbeat", token, {"revision": config["revision"]}))
    step(worker_api, job, "finish", container_id=container)
    return token, config["revision"]


def probe(collector, token, revision, healthy=True):
    payload = {"revision": revision, "handshake": int(datetime.now(UTC).timestamp()),
               "ping_ok": healthy, "diagnostic": "OK" if healthy else "NO_REPLY"}
    accepted(devices(collector, "connectivity", token, payload))


def target(isp, address, *, configured=True):
    site = make_site(isp, "Nodo QA")
    device = make(isp, "devices", {"name": "Equipo QA", "site_id": site["id"], "device_role": "NODE",
                                   "device_type": "Switch", "ip_address": address})
    if configured:
        accepted(request(isp, "PUT", CRM+"devices/"+device["id"]+"/icmp", {"requested": True, "interval_seconds": 10}))
    return device


def test_measurements_tenant_incidents_and_recovery(migrated, admin_id, monkeypatch):
    monkeypatch.setenv("SKNET_CONNECTIVITY_MODE", "simulation")
    with TestClient(app) as admin, TestClient(app) as isp, TestClient(app) as other, TestClient(worker) as work, TestClient(agent) as collector:
        authentication(admin)
        setup_isp(admin, isp, "icmp")
        setup_isp(admin, other, "icmp2")
        token, revision = establish(isp, work, collector, "a"*64)
        other_token, other_revision = establish(other, work, collector, "b"*64)
        probe(collector, token, revision)
        probe(collector, other_token, other_revision)
        configured = target(isp, "192.168.99.70")
        isolated = target(other, "192.168.99.70")
        unapproved = target(isp, "192.168.88.70")
        target(isp, None, configured=False)
        snapshot = accepted(devices(collector, "targets", token))
        foreign = accepted(devices(collector, "targets", other_token))
        assert snapshot["healthy"] and foreign["healthy"]
        assert [row["id"] for row in snapshot["items"]] == [configured["id"]]
        assert [row["id"] for row in foreign["items"]] == [isolated["id"]]
        epoch = snapshot["epoch"]
        selected = snapshot["items"][0]
        first = datetime.now(UTC) - timedelta(seconds=15)

        def sample(delta, received, latency=20):
            return {"device_id": configured["id"], "measurement_id": str(uuid4()), "revision": selected["revision"],
                    "epoch": epoch, "checked_at": (first+timedelta(seconds=delta)).isoformat(), "ip": selected["ip"],
                    "result": "REACHABLE" if received else "NO_REPLY", "sent": 5, "received": received,
                    "latency_min": latency if received else None, "latency_avg": latency if received else None,
                    "latency_max": latency if received else None}

        def send(item):
            return accepted(devices(collector, "results", token, {"items": [item]}))

        def state(name):
            panel = accepted(request(isp, "GET", "isp/monitoring/devices/"+configured["id"]))
            assert panel["status"] == name, panel
            return panel

        foreign_result = sample(0, 5) | {"device_id": isolated["id"]}
        assert send(foreign_result)["accepted"] == 0
        assert send(sample(0, 5) | {"device_id": unapproved["id"]})["accepted"] == 0
        valid = sample(0, 5)
        assert send(valid)["accepted"] == 1
        assert send(valid)["accepted"] == 0
        state("UP")
        send(sample(1, 5, 205))
        state("DEGRADED")
        send(sample(2, 4))
        state("DEGRADED")
        send(sample(3, 3))
        state("DEGRADED")
        send(sample(4, 0))
        send(sample(5, 0))
        assert len(state("DOWN")["incidents"]) == 1
        send(sample(4.5, 5))
        state("DOWN")
        send(sample(6, 5))
        state("DOWN")
        send(sample(7, 5))
        assert state("UP")["incidents"][0]["end_reason"] == "RECOVERED"
        for _ in range(3):
            probe(collector, token, revision, healthy=False)
        snapshot = accepted(devices(collector, "targets", token))
        assert not snapshot["healthy"]
        for index in range(8, 11):
            send(sample(index, 0))
        state("UNREACHABLE")
        open_items = accepted(request(isp, "GET", "isp/monitoring/incidents?active=true"))["items"]
        assert [item["kind"] for item in open_items] == ["VPN"]
        probe(collector, token, revision)
        epoch = accepted(devices(collector, "targets", token))["epoch"]
        send(sample(11, 5))
        state("UP")
        accepted(request(isp, "PUT", CRM+"devices/"+configured["id"]+"/icmp", {"requested": True, "interval_seconds": 20}))
        assert send(sample(12, 0))["accepted"] == 0
        migrated.execute("UPDATE connectivity.collectors SET last_heartbeat_at=now()-interval '31 seconds' WHERE docker_container_id=%s", ("a"*64,))
        state("STALE")
        assert accepted(request(other, "GET", "isp/monitoring/devices"))["items"][0]["id"] == isolated["id"]
        migrated.execute("UPDATE monitoring.icmp_checks SET received_at=now()-interval '31 days' WHERE measurement_id=%s",
                         (valid["measurement_id"],))
        engine = create_database_engine()
        try:
            with create_session_factory(engine)() as db:
                sweep(db, retain=True)
                db.commit()
        finally:
            engine.dispose()
        assert migrated.execute("SELECT id FROM monitoring.icmp_checks WHERE measurement_id=%s",
                                (valid["measurement_id"],)).fetchone() is None
        assert migrated.execute("SELECT count(*) FROM monitoring.incidents").fetchone() == (1,)
        assert migrated.execute("SELECT count(*) FROM monitoring.transport_incidents WHERE kind='COLLECTOR' AND ended_at IS NULL").fetchone() == (1,)
