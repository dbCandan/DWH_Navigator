"""Authentication responses containing public identifiers only."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ApplicationRoleValue = Literal["kullanici", "yonetici"]
# The role an account holds: one application role, or super_admin for the application administrator.
AccountRoleValue = Literal["kullanici", "yonetici", "super_admin"]


class AuthenticatedUser(BaseModel):
    public_id: UUID
    username: str
    display_name: str
    tenant_id: UUID
    role: AccountRoleValue | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    is_super_admin: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds.")
    user: AuthenticatedUser
