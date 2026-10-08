"""Super-admin account list, creation, role, activation and password-reset contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, StrictBool, field_validator

from app.domain.accounts import validate_display_name, validate_new_username
from app.schemas.auth.response import AccountRoleValue, ApplicationRoleValue


class UserSummary(BaseModel):
    public_id: UUID
    username: str
    display_name: str
    role: AccountRoleValue | None
    active: bool
    password_change_required: bool
    last_login_at: datetime | None
    created_at: datetime


class UserPage(BaseModel):
    items: list[UserSummary]
    page: int
    size: int
    total: int


class UserCreateRequest(BaseModel):
    username: str
    display_name: str
    role: ApplicationRoleValue

    @field_validator("username")
    @classmethod
    def normalized_username(cls, value: str) -> str:
        return validate_new_username(value)

    @field_validator("display_name")
    @classmethod
    def checked_display_name(cls, value: str) -> str:
        return validate_display_name(value)


class OneTimePassword(BaseModel):
    """Shown once in this response; no endpoint can read it again."""

    one_time_password: str
    one_time_password_expires_at: datetime


class UserCreated(OneTimePassword):
    user: UserSummary


class RoleChange(BaseModel):
    role: ApplicationRoleValue


class ActiveChange(BaseModel):
    active: StrictBool
