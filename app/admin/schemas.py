"""Schemi Pydantic per il pannello admin."""

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    """Schema utente in output."""

    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    allowed_modules: list[str]
    last_login: str | None
    created_at: str | None


class CreateUserRequest(BaseModel):
    """Schema creazione utente."""

    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    role: str = Field(default="user", pattern="^(admin|user)$")
    allowed_modules: list[str] = Field(default=["incassi_mubi", "connessione"])


class UpdateUserRequest(BaseModel):
    """Schema modifica utente."""

    full_name: str | None = None
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    allowed_modules: list[str] | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    """Schema reset password."""

    new_password: str = Field(min_length=8)


class ApplyUpdateRequest(BaseModel):
    """Schema richiesta aggiornamento."""

    branch: str = Field(default="main", min_length=1)


class AuditLogOut(BaseModel):
    """Schema voce audit log."""

    id: int
    user_id: int | None
    action: str
    detail: str | None
    timestamp: str | None


class CreatePecRequest(BaseModel):
    """Schema creazione connessione PEC."""

    label: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=5, max_length=200)
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1)


class UpdatePecRequest(BaseModel):
    """Schema modifica connessione PEC."""

    label: str | None = None
    email: str | None = None
    username: str | None = None
    password: str | None = None
    is_active: bool | None = None
