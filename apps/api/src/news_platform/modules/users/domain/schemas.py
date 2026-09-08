from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip()
        if value.count("@") != 1 or value.startswith("@") or value.endswith("@"):
            raise ValueError("invalid email")
        return value


class Registration(Credentials):
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("display name is required")
        return value


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    bio: str | None = Field(default=None, max_length=500)
    avatar_url: HttpUrl | None = None
    preferred_language: str = Field(
        min_length=2, max_length=35, pattern=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]+)*$"
    )
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class UserView(BaseModel):
    id: UUID
    email: str
    role: str
    display_name: str
    bio: str | None
    avatar_url: str | None
    preferred_language: str
    timezone: str | None


class AuthView(BaseModel):
    user: UserView
    csrf_token: str
    expires_at: datetime


class LogoutView(BaseModel):
    status: str = "logged_out"
