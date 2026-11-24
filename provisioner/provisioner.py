import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

import docker
from requests.exceptions import RequestException

from providers.docker_host import DockerHost
from providers.edge import RouterOS, Simulation
from rest import ApiError, request


MODE = os.getenv("SKNET_CONNECTIVITY_MODE", "disabled")
PATH = "/run/sknet-worker/api.sock"
PREFIX = "/api/v1/worker"
STATE = Path("/var/lib/sknet-provisioner")
LOG = logging.getLogger("provisioner")


class Failed(Exception):
    def __init__(self, code):
        self.code = code


def api(endpoint, data=None):
    return request(PATH, PREFIX, endpoint, data)


def identity(resource):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = STATE / (resource["id"] + ".json")
    info = json.loads(path.read_text()) if path.is_file() else {}
    if not info:
        key = subprocess.run(["wg", "genkey"], check=True, capture_output=True, text=True).stdout.strip()
        info = {"private_key": key, "token": secrets.token_urlsafe(32)}
    if resource["operation"] == "ROTATE_KEY" and info.get("rotation") != resource["job"]:
        info["rotation"] = resource["job"]
        info["token"] = secrets.token_urlsafe(32)
    fd, temporary = tempfile.mkstemp(dir=STATE)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(info, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    public = subprocess.run(["wg", "pubkey"], input=info["private_key"] + "\n", check=True,
                            capture_output=True, text=True).stdout.strip()
    return {"private_key": info["private_key"], "token": info["token"]}, {
        "public_key": public, "token_hash": hashlib.sha256(info["token"].encode()).hexdigest(),
    }


def process(resource, host, edge):
    def update(action, **data):
        return api(f"/jobs/{resource['job']}/{action}", dict(data, lease=resource["lease"]))

    code = "CONFIGURATION"
    try:
        if resource["mode"] != MODE or resource["simulated"] != (MODE == "simulation"):
            raise Failed(code)
        if resource["operation"] in {"DISABLE", "REMOVE"}:
            code = "RETIRE_FAILED"
            update("progress", step="RETIRING")
            if resource["tag"]:
                edge.remove(resource)
                host.retire(resource, remove=resource["operation"] == "REMOVE")
            update("finish")
            return
        code = "DOCKER_FAILED"
        inventory = host.inventory()
        if not resource["port"]:
            code = "ROUTEROS_FAILED"
            inventory["ports"] = sorted(set(inventory["ports"]) | set(edge.occupied(resource["first_port"], resource["last_port"])))
        allocation = update("reserve", inventory=inventory)
        if allocation.get("error"):
            raise Failed(allocation["error"])
        resource.update(allocation)
        code = "KEY_FAILED"
        update("progress", step="KEYS")
        secret, material = identity(resource)
        update("material", **material)
        code = "DOCKER_FAILED"
        update("progress", step="NETWORK")
        host.ensure_network(resource)
        update("progress", step="CONTAINER")
        container = host.ensure_container(resource, secret, restart=resource["operation"] == "ROTATE_KEY")
        code = "ROUTEROS_FAILED"
        update("progress", step="NAT")
        edge.ensure(resource)
        code = "DOCKER_FAILED"
        for _ in range(16):
            state = update("progress", step="VERIFYING")
            container.reload()
            if (container.status == "running" and state["heartbeat_fresh"]
                    and state["applied_revision"] == resource["revision"]
                    and container.exec_run(["wg", "show", "wg0", "public-key"]).output.decode().strip() == material["public_key"]):
                update("finish", container_id=container.id)
                LOG.info("Trabajo %s completado en modo %s", resource["job"], MODE)
                return
            time.sleep(2)
    except Failed as exc:
        code = exc.code
    except ApiError as exc:
        if exc.status == 409:
            LOG.info("Trabajo %s requiere reconciliación", resource["job"])
            return
        if exc.status >= 500:
            raise
    except docker.errors.APIError as exc:
        description = str(exc.explanation).lower()
        if any(cause in description for cause in ("port is already allocated", "address already in use", "ports are not available")):
            code = "PORT_CONFLICT"
    except (KeyError, OSError, ValueError, subprocess.SubprocessError):
        pass
    LOG.warning("Trabajo %s falló en %s", resource["job"], code)
    update("finish", error=code)


def run():
    client = docker.from_env(timeout=12)
    host = DockerHost(client)
    edge = None
    observed = 0
    verified = 0
    while True:
        try:
            if edge is None:
                edge = RouterOS() if MODE == "routeros" else Simulation()
            if time.monotonic() - observed >= 10:
                items = []
                verify_edge = time.monotonic() - verified >= 60
                states = {"running": "RUNNING", "exited": "EXITED", "created": "CREATED", "dead": "EXITED"}
                for resource in api("/inventory"):
                    container = host.optional(client.containers, resource["name"])
                    matching = container and container.labels.get("sknet.collector") == resource["id"]
                    item = {"id": resource["id"], "state": states.get(container.status, "UNKNOWN") if matching else "MISSING"}
                    if verify_edge and resource["tag"]:
                        try:
                            edge.verify(resource)
                        except (KeyError, OSError, ValueError):
                            item["error"] = "ROUTEROS_FAILED"
                    items.append(item)
                inventory = host.inventory()
                for offset in range(0, max(len(items), 1), 1024):
                    api("/observations", {"items": items[offset:offset+1024], "inventory": inventory})
                observed = time.monotonic()
                if verify_edge:
                    verified = observed
            job = api("/claim", {})
            if job:
                process(job, host, edge)
            else:
                time.sleep(2)
        except (ApiError, OSError, KeyError, ValueError, RequestException, docker.errors.DockerException) as exc:
            LOG.warning("Dependencia del provisioner no disponible (%s).", type(exc).__name__)
            time.sleep(5)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if "--check" in sys.argv:
        try:
            docker.from_env(timeout=3).ping()
        except docker.errors.DockerException:
            return 1
        return 0
    if MODE == "disabled":
        LOG.info("Aprovisionamiento deshabilitado.")
        while True:
            time.sleep(60)
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
