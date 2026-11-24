import ipaddress
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mode: str
    installation: str
    docker_pool: ipaddress.IPv4Network
    wg_pool: ipaddress.IPv4Network
    base_networks: tuple
    port_start: int
    port_end: int
    internal_port: int
    bind_ip: str
    endpoint: str
    mtu: int
    keepalive: int
    heartbeat: int
    stale: int

    @property
    def simulated(self):
        return self.mode == "simulation"


def stale_seconds():
    try:
        value = int(os.getenv("SKNET_COLLECTOR_STALE", "30"))
    except ValueError:
        return 30
    return value if 4 <= value <= 300 else 30


def load():
    env = os.getenv
    config = Config(
        env("SKNET_CONNECTIVITY_MODE", "disabled"),
        env("SKNET_INSTALLATION_ID", "sknet-dev"),
        ipaddress.IPv4Network(env("SKNET_DOCKER_POOL", "172.20.0.0/16")),
        ipaddress.IPv4Network(env("SKNET_WG_POOL", "10.200.1.0/24")),
        tuple(ipaddress.IPv4Network(net.strip()) for net in env("SKNET_PROTECTED_NETWORKS", "").split(",") if net.strip()),
        int(env("SKNET_UDP_FIRST", "51820")), int(env("SKNET_UDP_LAST", "51919")),
        int(env("SKNET_UDP_INTERNAL", "51820")),
        str(ipaddress.IPv4Address(env("SKNET_UDP_BIND", "127.0.0.1"))),
        env("SKNET_WG_ENDPOINT", "127.0.0.1"),
        int(env("SKNET_WG_MTU", "1420")), int(env("SKNET_WG_KEEPALIVE", "25")),
        int(env("SKNET_COLLECTOR_HEARTBEAT", "10")), int(env("SKNET_COLLECTOR_STALE", "30")),
    )
    if (
        config.mode not in {"disabled", "simulation", "routeros"}
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,22}", config.installation)
        or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}", config.endpoint)
        or config.docker_pool.prefixlen > 30 or config.wg_pool.prefixlen > 31
        or config.docker_pool.overlaps(config.wg_pool)
        or not 1 <= config.port_start <= config.port_end <= 65535
        or not 1 <= config.internal_port <= 65535 or not 576 <= config.mtu <= 1500
        or not 1 <= config.keepalive <= 65535 or not 2 <= config.heartbeat <= 60
        or not config.heartbeat * 2 <= config.stale <= 300
        or (config.mode == "routeros" and (
            not config.base_networks or ipaddress.IPv4Address(config.bind_ip).is_loopback
            or config.bind_ip == "0.0.0.0" or config.endpoint == "127.0.0.1"
        ))
    ):
        raise ValueError("Configuración de conectividad inválida.")
    return config
