import ipaddress
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from uuid import uuid4

from rest import ApiError


LOG = logging.getLogger("collector.scheduler")
COUNTS = re.compile(r"(\d+) packets transmitted, (\d+) (?:packets )?received")
RTT = re.compile(r"= ([\d.]+)/([\d.]+)/([\d.]+)/[\d.]+ ms")


def ready_targets(targets, pending, due, now, capacity):
    free_slots = capacity - len(pending)
    used_ips = {address for _, address in pending.values()}
    for target in sorted(targets, key=lambda item: due.get(item["id"], (0, 0))[1]):
        if free_slots <= 0:
            break
        key, addr = target["id"], target["ip"]
        revision, time_due = due.get(key, (0, 0))
        if key in pending or addr in used_ips or (revision == target["revision"] and now < time_due):
            continue
        yield target
        used_ips.add(addr)
        free_slots -= 1


def ping_target(target, epoch, *, interface="wg0"):
    host = str(ipaddress.IPv4Address(target["ip"]))
    count = int(target["packet_count"])
    wait = int(target["timeout_ms"]) / 1000
    result = {"device_id": target["id"], "measurement_id": str(uuid4()), "revision": target["revision"],
              "epoch": epoch, "ip": host, "checked_at": datetime.now(UTC).isoformat()}
    args = ["ping", "-4", "-n", "-I", interface, "-c", str(count), "-i", "0.2", "-W", str(wait), host]
    try:
        response = subprocess.run(args, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"},
                                  timeout=max(3, (count-1) * 0.2 + wait + 3))
        counts = COUNTS.search(response.stdout)
        rtt = RTT.search(response.stdout)
        if response.returncode in (0, 1) and counts:
            sent, received = map(int, counts.groups())
            if sent == count and (not received or rtt):
                result.update(sent=sent, received=received, result="REACHABLE" if received else "NO_REPLY")
                if received:
                    result.update(zip(("latency_min", "latency_avg", "latency_max"), map(float, rtt.groups())))
                return result
    except (OSError, subprocess.SubprocessError):
        pass
    return result | {"result": "ERROR", "diagnostic": "PING_ERROR"}


class Scheduler:
    def __init__(self, api, directory):
        self.api = api
        self.queue = directory / "icmp-spool.json"
        self.local_until = 0
        self.capacity = min(32, max(1, int(os.getenv("SKNET_ICMP_CONCURRENCY", "10"))))

    def visibility(self, healthy, heartbeat=10):
        self.local_until = time.monotonic() + max(30, 2 * heartbeat + 5) if healthy else 0

    def start(self):
        Thread(target=self.run, name="icmp-scheduler", daemon=True).start()

    def pending(self):
        try:
            samples = json.loads(self.queue.read_text())
            return self.recent(samples)
        except (OSError, ValueError, TypeError, KeyError):
            return []

    @staticmethod
    def recent(samples):
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        return [sample for sample in samples if datetime.fromisoformat(sample["checked_at"]) >= cutoff][-10000:]

    def persist(self, batch):
        path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.queue.parent, delete=False) as stream:
                path = Path(stream.name)
                json.dump(batch, stream, separators=(",", ":"))
            path.replace(self.queue)
        except OSError:
            LOG.warning("No se pudo guardar la cola local de ICMP.")
        finally:
            if path:
                path.unlink(missing_ok=True)

    def run(self):
        snapshot = {"items": [], "healthy": False, "epoch": 1}
        next_config = next_upload = expires = 0
        backoff = 2
        queued = self.pending()
        pending = {}
        due = {}
        with ThreadPoolExecutor(max_workers=self.capacity) as executor:
            while True:
                now = time.monotonic()
                if now >= next_config:
                    try:
                        snapshot = self.api("/targets")
                        expires = time.monotonic() + 90
                        valid = {item["id"] for item in snapshot["items"]}
                        due = {key: value for key, value in due.items() if key in valid}
                    except (OSError, ApiError, ValueError) as exc:
                        if isinstance(exc, ApiError) and exc.status in (401, 403):
                            snapshot = {"items": [], "healthy": False, "epoch": 1}
                            queued = []
                            self.persist(queued)
                    next_config = time.monotonic() + 5
                changed = False
                for key, (future, address) in tuple(pending.items()):
                    if future.done():
                        try:
                            queued.append(future.result())
                            changed = True
                        except (TypeError, ValueError):
                            LOG.warning("El destino ICMP recibido no es válido.")
                        del pending[key]
                if changed:
                    count = len(queued)
                    queued = self.recent(queued)
                    if count > len(queued):
                        LOG.warning("Se descartaron %s muestras por antigüedad o capacidad.", count-len(queued))
                    self.persist(queued)
                if queued and now >= next_upload:
                    try:
                        self.api("/results", {"items": queued[:100]})
                        queued = queued[100:]
                        self.persist(queued)
                        backoff = 2
                    except (OSError, ApiError, ValueError) as exc:
                        if isinstance(exc, ApiError) and exc.status in (401, 403):
                            snapshot = {"items": [], "healthy": False, "epoch": 1}
                            queued = []
                            self.persist(queued)
                        backoff = min(60, backoff*2)
                    next_upload = time.monotonic() + backoff
                if snapshot["healthy"] and now < self.local_until and now < expires:
                    for target in ready_targets(snapshot["items"], pending, due, now, self.capacity):
                        key, addr = target["id"], target["ip"]
                        future = executor.submit(ping_target, target, snapshot["epoch"])
                        pending[key] = (future, addr)
                        due[key] = (target["revision"], now + target["interval_seconds"])
                time.sleep(0.5)
