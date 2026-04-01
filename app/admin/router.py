"""Router pannello admin: gestione utenti, aggiornamenti, audit log."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin import service as admin_service
from app.admin import update_service
from app.auth.dependencies import require_admin
from app.database import get_db
from app.models import User, log_audit

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---

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
    allowed_modules: list[str] = Field(default=["incassi_mubi"])


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


# --- Helpers ---

def _user_to_dict(u: User) -> dict:
    """Converte un User ORM in dict per la risposta."""
    return {
        "id": u.id,
        "username": u.username,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
        "allowed_modules": u.get_modules(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


# --- Endpoints ---

@router.get("/users")
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Lista tutti gli utenti (solo admin)."""
    users = admin_service.list_users(db)
    return [_user_to_dict(u) for u in users]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    request: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Crea un nuovo utente (solo admin)."""
    existing = admin_service.get_user_by_username(db, request.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{request.username}' gia' in uso",
        )
    user = admin_service.create_user(
        db,
        username=request.username,
        full_name=request.full_name,
        password=request.password,
        role=request.role,
        allowed_modules=request.allowed_modules,
        created_by_id=admin.id,
    )
    return _user_to_dict(user)


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    request: UpdateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Modifica un utente (solo admin)."""
    user = admin_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    user = admin_service.update_user(
        db,
        user=user,
        full_name=request.full_name,
        role=request.role,
        allowed_modules=request.allowed_modules,
        is_active=request.is_active,
        updated_by_id=admin.id,
    )
    return _user_to_dict(user)


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: int,
    request: ResetPasswordRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """Reset password di un utente (solo admin)."""
    user = admin_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    admin_service.reset_password(
        db,
        user=user,
        new_password=request.new_password,
        reset_by_id=admin.id,
    )


@router.get("/audit-log")
def get_audit_log(
    page: int = 1,
    per_page: int = 50,
    action: str | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Log operazioni paginato con filtri (solo admin)."""
    logs, total = admin_service.get_audit_log(
        db, page=page, per_page=per_page, action_filter=action,
    )
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "detail": log.detail,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
            for log in logs
        ],
    }


# --- Aggiornamenti ---

@router.get("/updates/branches")
def list_branches(admin: User = Depends(require_admin)) -> dict:
    """Elenca i branch remoti disponibili."""
    try:
        branches = update_service.list_remote_branches()
        current = update_service.get_current_branch()
        return {"current_branch": current, "branches": branches}
    except Exception as exc:
        logger.exception("Errore lettura branch remoti")
        raise HTTPException(status_code=500, detail=f"Errore git: {exc}") from exc


@router.get("/updates/check")
def check_updates(
    branch: str = "main",
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Controlla se ci sono aggiornamenti per il branch specificato."""
    try:
        result = update_service.check_for_updates(branch)
        log_audit(db, "update_check", user_id=admin.id,
                  detail=f'{{"branch":"{branch}","behind":{result["commits_behind"]}}}')
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Errore controllo aggiornamenti")
        raise HTTPException(status_code=500, detail=f"Errore git: {exc}") from exc


@router.post("/updates/apply")
def apply_update(
    request: ApplyUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Applica l'aggiornamento dal branch selezionato."""
    try:
        result = update_service.apply_update(request.branch)
        log_audit(
            db, "update_applied", user_id=admin.id,
            detail=(
                f'{{"branch":"{result["new_branch"]}",'
                f'"old_sha":"{result["old_sha"]}",'
                f'"new_sha":"{result["new_sha"]}"}}'
            ),
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Errore applicazione aggiornamento")
        raise HTTPException(status_code=500, detail=f"Errore git: {exc}") from exc
