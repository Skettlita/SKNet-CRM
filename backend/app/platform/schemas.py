from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, EmailStr, Field, StringConstraints, field_validator, model_validator

from app.auth.schemas import Input, Name, Note


CompanyStatus = Literal["ACTIVE", "INACTIVE", "CLOSED"]
SubscriptionStatus = Literal["TRIAL", "ACTIVE", "GRACE", "SUSPENDED", "CANCELLED"]
TicketStatus = Literal["OPEN", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", "CANCELLED"]
Priority = Literal["LOW", "NORMAL", "HIGH", "CRITICAL"]
Price = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Days = Annotated[int, Field(ge=1, le=36500)]
Limit = Annotated[int, Field(ge=1, le=2147483647)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class CompanyWrite(Input):
    name: Name
    tax_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9(). -]{5,30}$")] | None = None
    email: EmailStr | None = None
    timezone: Annotated[str, StringConstraints(max_length=80)]

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Zona horaria inválida.") from None
        return value


class CompanyState(Input):
    status: Literal["ACTIVE", "INACTIVE"]
    reason: Note


class PlanTerms(Input):
    description: Description = ""
    price: Price
    currency: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{3}$")]
    billing_period: Literal["MONTHLY", "YEARLY"]
    duration_days: Days | None = None
    max_clients: Limit | None = None
    max_users: Limit | None = None
    max_devices: Limit | None = None
    min_poll_interval_seconds: Annotated[int, Field(ge=5, le=86400)] | None = None
    retention_days: Days | None = None
    features: list[Annotated[str, StringConstraints(max_length=60)]] = Field(max_length=50)


class PlanCreate(PlanTerms):
    code: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z][A-Z0-9_]{1,39}$")]
    name: Name


class PlanEdit(PlanTerms):
    name: Name


class PlanState(Input):
    active: bool


class SubscriptionWrite(Input):
    plan_version_id: UUID
    status: SubscriptionStatus
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    reason: Note

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.starts_at is not None and self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("El vencimiento debe ser posterior al inicio.")
        return self


class TicketCreate(Input):
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=160)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=5000)]
    priority: Priority = "NORMAL"


class TicketEdit(Input):
    priority: Priority
    status: TicketStatus
    assigned_staff_id: UUID | None = None
    reason: Note


class TicketReply(Input):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=5000)]
    internal: bool = False
