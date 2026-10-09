"""Authentication request bodies."""

from pydantic import BaseModel, Field, SecretStr

from app.domain.accounts import USERNAME_MAX_LENGTH
from app.domain.password_policy import PASSWORD_MAX_LENGTH

# A chosen password longer than the policy allows is answered by the policy (``too_long``), not by
# request validation; this bound only caps the work one request can ask for.
NEW_PASSWORD_INPUT_MAX_LENGTH = 1024


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=USERNAME_MAX_LENGTH)
    password: SecretStr = Field(max_length=PASSWORD_MAX_LENGTH)


class PasswordChangeRequest(BaseModel):
    username: str = Field(min_length=1, max_length=USERNAME_MAX_LENGTH)
    # The current password, or the one-time password the super admin handed over.
    current_password: SecretStr = Field(max_length=PASSWORD_MAX_LENGTH)
    new_password: SecretStr = Field(max_length=NEW_PASSWORD_INPUT_MAX_LENGTH)
