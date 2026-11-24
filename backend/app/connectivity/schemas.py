import base64
import binascii
from ipaddress import IPv4Network
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator

from app.auth.schemas import Input


PublicKey = Annotated[str, StringConstraints(min_length=44, max_length=44)]
Code = Literal["DOCKER_FAILED", "PORT_CONFLICT", "DOCKER_POOL", "WG_POOL", "UDP_POOL",
               "ROUTEROS_FAILED", "ROUTE_CONFLICT", "KEY_FAILED", "LEASE_EXPIRED",
               "COLLECTOR_STALE", "CONFIGURATION", "RETIRE_FAILED", "UPGRADE_FAILED", "ROLLBACK_FAILED"]
Step = Literal["RESERVING", "KEYS", "NETWORK", "CONTAINER", "NAT", "VERIFYING", "RETIRING", "UPGRADING", "ROLLBACK"]
Image = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


def check_key(value):
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Clave pública no válida.") from None
    if len(raw) != 32 or not any(raw) or base64.b64encode(raw).decode() != value:
        raise ValueError("Clave pública no válida.")
    return value


class Routes(Input):
    networks: list[IPv4Network] = Field(min_length=1, max_length=32)

    @field_validator("networks")
    @classmethod
    def disjoint(cls, values):
        if any(net.prefixlen < 8 or not any(net.subnet_of(IPv4Network(block)) for block in (
            "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"
        )) for net in values):
            raise ValueError("Usa subredes IPv4 privadas RFC 1918 específicas.")
        if any(a.overlaps(b) for index, a in enumerate(values) for b in values[index + 1:]):
            raise ValueError("Las redes autorizadas no deben solaparse.")
        return sorted(values)


class Peer(Routes):
    public_key: PublicKey

    @field_validator("public_key")
    @classmethod
    def valid(cls, value):
        return check_key(value)


class Inventory(Input):
    networks: list[IPv4Network] = Field(default_factory=list, max_length=4096)
    ports: list[Annotated[int, Field(ge=1, le=65535)]] = Field(default_factory=list, max_length=65535)


class Lease(Input):
    lease: UUID


class Reservation(Lease):
    inventory: Inventory


class Material(Lease):
    public_key: PublicKey
    token_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

    @field_validator("public_key")
    @classmethod
    def valid(cls, value):
        return check_key(value)


class Progress(Lease):
    step: Step
    reset_heartbeat: bool = False


class Completion(Lease):
    container_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    error: Code | None = None
    image: Image | None = None
    rolled_back: bool = False


class AdminAction(Input):
    expected_image: Image | None = None


class Observation(Input):
    id: UUID
    state: Literal["RUNNING", "EXITED", "MISSING", "CREATED", "UNKNOWN"]
    error: Literal["ROUTEROS_FAILED"] | None = None
    image: Image | None = None
    available_image: Image | None = None


class DockerResource(Input):
    id: UUID
    company: UUID
    kind: Literal["container", "network", "volume"]
    name: Annotated[str, StringConstraints(max_length=255)]


class Observations(Input):
    items: list[Observation] = Field(max_length=1024)
    inventory: Inventory
    resources: list[DockerResource] | None = Field(default=None, max_length=4096)


class Probe(Input):
    revision: int = Field(ge=1)
    handshake: int = Field(default=0, ge=0, le=4102444800)
    ping_ok: bool = False
    diagnostic: Literal["NO_PEER", "WG_ERROR", "NO_HANDSHAKE", "NO_REPLY", "OK"]


class Heartbeat(Input):
    revision: int = Field(ge=1)
