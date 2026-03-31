"""Router autenticazione: login, logout, profilo utente."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.admin.service import verify_password
from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token
from app.auth.rate_limit import RateLimitExceeded, check_rate_limit
from app.database import get_db
from app.models import User, log_audit

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
def login(request: LoginRequest, req: Request, db: Session = Depends(get_db)) -> LoginResponse:
    """Autentica l'utente e restituisce un token JWT (max 5 tentativi/min per IP)."""
    client_ip = req.client.host if req.client else "unknown"
    try:
        check_rate_limit(client_ip)
    except RateLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Troppi tentativi di login. Riprova tra un minuto.",
        )
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
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide",
        )

    # Aggiorna ultimo accesso
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    modules = user.get_modules()

    token = create_access_token(
        data={"sub": user.username, "role": user.role, "modules": modules}
    )

    log_audit(db, "user_login", user_id=user.id, detail={"username": user.username})

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
    return UserProfile(
        username=current_user.username,
        full_name=current_user.full_name,
        role=current_user.role,
        allowed_modules=current_user.get_modules(),
    )
