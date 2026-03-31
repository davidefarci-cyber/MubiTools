"""Router autenticazione: login, logout, profilo utente."""

import json
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token
from app.database import get_db
from app.models import User

router = APIRouter()


class LoginRequest(BaseModel):
    """Schema richiesta login."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Schema risposta login con token JWT."""

    access_token: str
    token_type: str = "bearer"
    username: str
    full_name: str
    role: str
    allowed_modules: list[str]


class UserProfile(BaseModel):
    """Schema profilo utente."""

    username: str
    full_name: str
    role: str
    allowed_modules: list[str]


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Autentica l'utente e restituisce un token JWT."""
    user = db.query(User).filter(User.username == request.username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account disabilitato",
        )
    if not bcrypt.checkpw(
        request.password.encode("utf-8"),
        user.hashed_password.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide",
        )

    # Aggiorna ultimo accesso
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    modules = json.loads(user.allowed_modules) if user.allowed_modules else []

    token = create_access_token(
        data={"sub": user.username, "role": user.role, "modules": modules}
    )

    return LoginResponse(
        access_token=token,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        allowed_modules=modules,
    )


@router.get("/me", response_model=UserProfile)
def get_me(current_user: User = Depends(get_current_user)) -> UserProfile:
    """Restituisce i dati dell'utente corrente."""
    modules = json.loads(current_user.allowed_modules) if current_user.allowed_modules else []
    return UserProfile(
        username=current_user.username,
        full_name=current_user.full_name,
        role=current_user.role,
        allowed_modules=modules,
    )
