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
        if resource["operation"] == "UPGRADE":
            raise Failed("KEY_FAILED")
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


def verify_container(container, resource, material, update, *, image=None):
    for _ in range(16):
        state = update("progress", step="VERIFYING")
        container.reload()
        if (container.status == "running" and (image is None or container.attrs["Image"] == image)
                and state["heartbeat_fresh"] and state["applied_revision"] == resource["revision"]
                and container.exec_run(["wg", "show", "wg0", "public-key"]).output.decode().strip()
                == material["public_key"]):
            return True
        time.sleep(2)
    return False


def replace_container(host, resource, secret, image, update, step):
    container = host.owned(resource, host.client.containers, resource["name"])
    if container and container.attrs["Image"] != image:
        host.remove_for_replacement(resource, container)
    update("progress", step=step, reset_heartbeat=True)
    return host.ensure_container(resource, secret, image=image)


def upgrade(resource, host, update):
    previous, desired = resource["previous_image"], resource["desired_image"]
    if not (previous and desired and previous != desired and resource["port"] and resource["tag"]):
        raise Failed("UPGRADE_FAILED")
    if (not host.owned(resource, host.client.volumes, resource["name"] + "-data")
            or not host.owned(resource, host.client.networks, resource["network_name"])
            or not host.optional(host.client.images, previous)):
        raise Failed("UPGRADE_FAILED")
    host.ensure_network(resource)
    existing = host.owned(resource, host.client.containers, resource["name"])
    if existing and existing.attrs["Image"] not in {previous, desired}:
        raise Failed("UPGRADE_FAILED")
    secret, material = identity(resource)
    update("material", **material)
    if not resource["rollback_started"] and host.optional(host.client.images, desired):
        try:
            update("progress", step="UPGRADING")
            candidate = replace_container(host, resource, secret, desired, update, "UPGRADING")
            if verify_container(candidate, resource, material, update, image=desired):
                update("finish", container_id=candidate.id, image=desired)
                return
        except (docker.errors.APIError, OSError, ValueError):
            LOG.warning("No pudo activarse la imagen solicitada para el trabajo %s", resource["job"])
    try:
        update("progress", step="ROLLBACK")
        restored = replace_container(host, resource, secret, previous, update, "ROLLBACK")
        if verify_container(restored, resource, material, update, image=previous):
            update("finish", container_id=restored.id, image=previous, rolled_back=True, error="UPGRADE_FAILED")
            return
    except (docker.errors.APIError, OSError, ValueError):
        pass
    raise Failed("ROLLBACK_FAILED")


def process(resource, host, edge):
    def update(action, **data):
        return api(f"/jobs/{resource['job']}/{action}", dict(data, lease=resource["lease"]))

    code = "CONFIGURATION"
    try:
        if resource["mode"] != MODE or resource["simulated"] != (MODE == "simulation"):
            raise Failed(code)
        if resource["operation"] == "UPGRADE":
            code = "UPGRADE_FAILED"
            upgrade(resource, host, update)
            return
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
        pinned = resource.get("current_image")
        existing = host.owned(resource, host.client.containers, resource["name"]) if pinned else None
        if pinned and (not existing or existing.attrs["Image"] != pinned):
            if resource["operation"] != "RECONCILE" or not host.optional(host.client.images, pinned):
                raise Failed("DOCKER_FAILED")
            container = replace_container(host, resource, secret, pinned, update, "CONTAINER")
        else:
            container = host.ensure_container(resource, secret, restart=resource["operation"] == "ROTATE_KEY", image=pinned)
        code = "ROUTEROS_FAILED"
        update("progress", step="NAT")
        edge.ensure(resource)
        code = "DOCKER_FAILED"
        if verify_container(container, resource, material, update, image=pinned):
            update("finish", container_id=container.id, image=container.attrs["Image"])
            LOG.info("Trabajo %s completado en modo %s", resource["job"], MODE)
            return
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
                available = host.available_image()
                resources = api("/inventory")
                installation = resources[0]["installation"] if resources else os.getenv("SKNET_INSTALLATION_ID")
                for resource in resources:
                    container = host.optional(client.containers, resource["name"])
                    matching = container and all(container.labels.get(key) == value for key, value in host.labels(resource).items())
                    item = {"id": resource["id"], "state": states.get(container.status, "UNKNOWN") if matching else "MISSING",
                            "image": container.attrs["Image"] if matching else None, "available_image": available}
                    if verify_edge and resource["tag"]:
                        try:
                            edge.verify(resource)
                        except (KeyError, OSError, ValueError):
                            item["error"] = "ROUTEROS_FAILED"
                    items.append(item)
                inventory = host.inventory()
                for offset in range(0, max(len(items), 1), 1024):
                    payload = {"items": items[offset:offset+1024], "inventory": inventory}
                    if offset == 0 and installation:
                        payload["resources"] = host.labelled_resources(installation)
                    api("/observations", payload)
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
