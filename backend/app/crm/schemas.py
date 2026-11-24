import re
from datetime import date
from decimal import Decimal
from ipaddress import ip_address
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, EmailStr, Field, StringConstraints, field_validator, model_validator

from app.auth.schemas import Input, Name, Note


Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9(). -]{5,30}$")]
Price = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Currency = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{3}$")]
Speed = Annotated[int, Field(ge=1, le=2147483647)]
SiteType = Literal["CLIENT_SITE", "WAREHOUSE", "OFFICE", "NODE", "TOWER", "WORKSHOP", "OTHER"]
Role = Literal["NODE", "INTERMEDIATE", "ENDPOINT"]
ServiceStatus = Literal["PENDING", "ACTIVE", "SUSPENDED", "CANCELLED"]


def address(value, *, ipv4_only=False):
    if value is None:
        return None
    parsed = ip_address(value)
    if ipv4_only and parsed.version != 4 or getattr(parsed, "scope_id", None):
        raise ValueError("Dirección IP no válida para este campo.")
    return str(parsed)


class Client(Input):
    client_code: Short
    client_type: Literal["PERSON", "COMPANY"]
    name: Name
    document_type: Short | None = None
    document_number: Short | None = None
    email: EmailStr | None = None
    phone: Phone | None = None
    observations: Long | None = None


class Contact(Input):
    name: Name
    position: Short | None = None
    email: EmailStr | None = None
    phone: Phone | None = None
    is_primary: bool = False


class Address(Input):
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=400)]
    city: Short | None = None
    address_type: Literal["BILLING", "LEGAL", "OTHER"] = "OTHER"


class ClientNote(Input):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=4000)]


class InternetPlan(Input):
    name: Name
    service_type: Short = "INTERNET"
    description: Long | None = None
    observations: Long | None = None
    download_mbps: Speed | None = None
    upload_mbps: Speed | None = None
    monthly_price: Price
    currency: Currency = "BOB"


class Site(Input):
    name: Name
    site_type: SiteType
    client_id: UUID | None = None
    address: Long | None = None
    city: Short | None = None
    latitude: Annotated[Decimal, Field(ge=-90, le=90, decimal_places=6)] | None = None
    longitude: Annotated[Decimal, Field(ge=-180, le=180, decimal_places=6)] | None = None
    description: Long | None = None

    @model_validator(mode="after")
    def association(self):
        if (self.site_type == "CLIENT_SITE") != (self.client_id is not None):
            raise ValueError("El tipo Sitio de cliente requiere un cliente. Los demás tipos son infraestructura propia.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Registra latitud y longitud juntas.")
        return self


class Service(Input):
    client_id: UUID
    site_id: UUID
    plan_id: UUID
    monthly_price: Price | None = None
    currency: Currency | None = None
    contracted_on: date | None = None
    access_method: Literal["PPPOE", "DHCP", "STATIC", "OTHER"]
    ip_assignment: Literal["DYNAMIC", "FIXED"] | None = None
    pppoe_username: Short | None = None
    service_ip: Short | None = None
    access_mac: Short | None = None
    access_router_id: UUID | None = None
    technical_notes: Long | None = None
    observations: Long | None = None

    @field_validator("service_ip")
    @classmethod
    def check_ip(cls, value):
        return address(value)

    @field_validator("access_mac")
    @classmethod
    def check_mac(cls, value):
        if value and not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", value):
            raise ValueError("Usa una MAC con formato AA:BB:CC:DD:EE:FF.")
        return value.lower() if value else None

    @model_validator(mode="after")
    def validate_access(self):
        if self.pppoe_username and self.access_method != "PPPOE":
            raise ValueError("El usuario PPPoE solo corresponde a servicios PPPoE.")
        if self.access_method == "STATIC":
            if self.ip_assignment == "DYNAMIC":
                raise ValueError("El acceso estático requiere asignación fija.")
            self.ip_assignment = "FIXED"
        return self


class Device(Input):
    name: Name
    site_id: UUID
    service_id: UUID | None = None
    device_type: Short
    device_role: Role
    brand: Short | None = None
    model: Short | None = None
    description: Long | None = None
    ip_address: Short | None = None

    @field_validator("ip_address")
    @classmethod
    def check_ip(cls, value):
        return address(value, ipv4_only=True)


class State(Input):
    active: bool
    reason: Note


class ServiceState(Input):
    status: ServiceStatus
    reason: Note
    activated_at: AwareDatetime | None = None


class IcmpProfile(Input):
    requested: bool
    interval_seconds: int = Field(30, ge=5, le=86400)
    timeout_ms: int = Field(2000, ge=100, le=10000)
    packet_count: int = Field(5, ge=1, le=10)
    latency_warning_ms: Decimal = Field(Decimal("200"), gt=0, max_digits=12, decimal_places=3)
    loss_warning_pct: Decimal = Field(Decimal("0"), ge=0, le=99.99, decimal_places=2)
    loss_failure_pct: Decimal = Field(Decimal("30"), ge=0, le=99.99, decimal_places=2)
    failure_threshold: int = Field(3, ge=1, le=32767)
    recovery_threshold: int = Field(2, ge=1, le=32767)

    @model_validator(mode="after")
    def valid_thresholds(self):
        if self.loss_warning_pct > self.loss_failure_pct:
            raise ValueError("El umbral de aviso de pérdida no puede superar el de fallo.")
        return self
