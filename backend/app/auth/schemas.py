from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9_.-]{3,64}$")]
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Identity(Input):
    name: Name
    username: Username
    email: EmailStr

    @field_validator("username", "email")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.lower()


class Login(Input):
    identifier: Identifier
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class PasswordPair(Input):
    password: Password
    confirm_password: Password

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Las contraseñas no coinciden.")
        return self


class CompanyRegistration(Identity, PasswordPair):
    company: Name
    tax_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9(). -]{5,30}$")]


class Signup(CompanyRegistration):
    accept_terms: bool


class UserWrite(Identity):
    role_ids: list[UUID] = Field(max_length=50)


class UserEdit(Identity):
    role_ids: list[UUID] | None = Field(default=None, max_length=50)
    active: bool


class RoleWrite(Input):
    name: Name
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=240)] = ""
    permissions: list[Annotated[str, StringConstraints(max_length=80)]] = Field(max_length=100)


class ChangePassword(PasswordPair):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class RequestReset(Input):
    email: EmailStr


class ConfirmReset(PasswordPair):
    token: Annotated[str, StringConstraints(min_length=32, max_length=128)]


class SupportReset(Input):
    identifier: Identifier
    reason: Note
    identity_verified: bool


class ProfileWrite(Input):
    name: Name
    compact_view: bool


class SettingsWrite(Input):
    public_signup_enabled: bool
    monthly_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    trial_days: int | None = Field(default=None, ge=1, le=3650)
    max_users: int | None = Field(default=None, ge=1, le=100000)


class VerifyEmail(Input):
    token: Annotated[str, StringConstraints(min_length=32, max_length=128)]
