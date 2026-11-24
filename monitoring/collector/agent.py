import json
import logging
from pathlib import Path
import subprocess
import tempfile
import time

from rest import ApiError, request
from scheduler import Scheduler


STATE = Path("/state")
PATH = "/run/sknet-collector/api.sock"
PREFIX = "/api/v1/collector"
LOG = logging.getLogger("collector")


def api(endpoint, data=None):
    identity = json.loads((STATE / "identity.json").read_text())
    return request(PATH, PREFIX, endpoint, data, token=identity["token"])


def command(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=5)


def firewall(port):
    rules = (
        ("OUTPUT", "-o", "eth0", "-m", "mark", "!", "--mark", "51820", "-j", "DROP"),
        ("INPUT", "-i", "eth0", "!", "-p", "udp", "-j", "DROP"),
        ("INPUT", "-i", "eth0", "-p", "udp", "!", "--dport", str(port), "-j", "DROP"),
        ("FORWARD", "-j", "DROP"),
    )
    for chain, *rule in rules:
        if command("iptables", "-C", chain, *rule, check=False).returncode:
            command("iptables", "-I", chain, *rule)


def configure(config, secret, previous):
    if command("ip", "link", "show", "wg0", check=False).returncode:
        command("ip", "link", "add", "wg0", "type", "wireguard")
    command("ip", "address", "replace", config["local_ip"], "dev", "wg0")
    command("ip", "link", "set", "wg0", "mtu", str(config["mtu"]))
    content = f"[Interface]\nPrivateKey = {secret}\nListenPort = {config['port']}\nFwMark = 51820\n"
    wanted = set()
    if config["public_key"]:
        wanted = set(config["networks"])
        allowed = ", ".join([config["remote_ip"] + "/32", *sorted(wanted)])
        content += f"[Peer]\nPublicKey = {config['public_key']}\nAllowedIPs = {allowed}\n"
    with tempfile.NamedTemporaryFile(mode="w") as stream:
        stream.write(content)
        stream.flush()
        command("wg", "syncconf", "wg0", stream.name)
    firewall(config["port"])
    command("ip", "link", "set", "wg0", "up")
    for obsolete in previous - wanted:
        command("ip", "route", "del", obsolete, "dev", "wg0", check=False)
    for network in sorted(wanted):
        command("ip", "route", "replace", network, "dev", "wg0")
    return wanted


def diagnose(config):
    result = {"revision": config["revision"], "handshake": 0, "ping_ok": False, "diagnostic": "NO_PEER"}
    if config["public_key"]:
        ping = command("ping", "-I", "wg0", "-c", "1", "-W", "2", config["remote_ip"], check=False)
        handshake = command("wg", "show", "wg0", "latest-handshakes")
        for record in handshake.stdout.splitlines():
            peer, timestamp = record.split()
            if peer == config["public_key"]:
                result["handshake"] = int(timestamp)
        result["ping_ok"] = ping.returncode == 0
        result["diagnostic"] = ("NO_HANDSHAKE" if time.time() - result["handshake"] > 180
                                else "OK" if result["ping_ok"] else "NO_REPLY")
    return result


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    installed = None
    networks = set()
    config = None
    previous_problem = None
    cache = STATE / "config.json"
    checks = Scheduler(api, STATE)
    checks.start()
    while True:
        delay = 10
        try:
            identity = json.loads((STATE / "identity.json").read_text())
            online = True
            try:
                config = api("/config")
            except (ApiError, OSError) as exc:
                online = False
                if isinstance(exc, ApiError) and exc.status in {401, 403}:
                    command("ip", "link", "del", "wg0", check=False)
                    cache.unlink(missing_ok=True)
                    installed, networks = None, set()
                    raise
                if not cache.is_file():
                    raise
                config = json.loads(cache.read_text())
            delay = config["heartbeat"]
            if installed != config:
                networks = configure(config, identity["private_key"], networks)
                if online:
                    with tempfile.NamedTemporaryFile(mode="w", dir=STATE, delete=False) as spool:
                        json.dump(config, spool)
                    Path(spool.name).replace(cache)
                installed = config
                LOG.info("WireGuard configurado. Modo: %s.", "simulación" if config["simulated"] else "RouterOS")
            if online:
                api("/heartbeat", {"revision": installed["revision"]})
            probe = diagnose(config)
            checks.visibility(probe["ping_ok"] and bool(probe["handshake"]), config["heartbeat"])
            if online:
                api("/connectivity", probe)
            previous_problem = None
        except (OSError, ApiError, ValueError, subprocess.SubprocessError) as exc:
            checks.visibility(False)
            problem = type(exc).__name__
            if problem != previous_problem:
                LOG.warning("Collector en espera (%s).", problem)
                previous_problem = problem
            if config and isinstance(exc, subprocess.SubprocessError):
                try:
                    api("/diagnostics", {"revision": config["revision"], "diagnostic": "WG_ERROR"})
                except (ApiError, OSError):
                    pass
        time.sleep(delay)


if __name__ == "__main__":
    main()
