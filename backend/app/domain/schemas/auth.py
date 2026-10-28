"""Public authentication payloads. Secret values never appear in model reprs."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class AuthPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Identity(AuthPayload):
    tenant_slug: Annotated[
        str, Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    ]
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class Login(Identity):
    password: SecretStr = Field(min_length=1, max_length=1024)


class Register(Identity):
    password: SecretStr = Field(min_length=12, max_length=1024)
    full_name: str = Field(min_length=1, max_length=255)
    tenant_name: str = Field(min_length=1, max_length=255)


class Refresh(AuthPayload):
    refresh_token: SecretStr = Field(min_length=1, max_length=1024)


class ResetConfirm(AuthPayload):
    token: SecretStr = Field(min_length=1, max_length=4096)
    password: SecretStr = Field(min_length=12, max_length=1024)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class Message(BaseModel):
    message: str
