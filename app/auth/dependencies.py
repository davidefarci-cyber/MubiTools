"""Dependency injection per l'autenticazione."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token
from app.database import get_db
from app.models import User

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Estrae e valida l'utente corrente dal token JWT."""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token non valido o scaduto",
        )
    username: str | None = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token non valido",
        )
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utente non trovato o disabilitato",
        )
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Verifica che l'utente corrente sia un admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accesso riservato agli amministratori",
        )
    return current_user


def require_module(module_name: str) -> Callable[[User], User]:
    """Factory: restituisce una dependency FastAPI che verifica l'accesso al modulo."""

    def _checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.has_module(module_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Modulo non abilitato",
            )
        return current_user

    return _checker
