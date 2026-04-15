"""Router pannello admin: gestione utenti, aggiornamenti, audit log, backup/restore DB."""

import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin import service as admin_service
from app.admin import update_service
from app.auth.dependencies import require_admin
from app.config import BASE_DIR
from app.database import Base, SessionLocal, engine, get_db
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


# --- Backup / Restore Database ---

_DB_PATH = Path(str(engine.url).replace("sqlite:///", ""))
_BACKUPS_DIR = BASE_DIR / "data" / "backups"


@router.get("/db/backup")
def backup_database(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Scarica un backup del database SQLite corrente."""
    if not _DB_PATH.exists():
        raise HTTPException(status_code=404, detail="File database non trovato")

    _BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"mubi_backup_{ts}.db"
    backup_path = _BACKUPS_DIR / filename

    # Usa backup API di SQLite per un dump consistente
    src_conn = sqlite3.connect(str(_DB_PATH))
    dst_conn = sqlite3.connect(str(backup_path))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    log_audit(db, "db_backup", user_id=admin.id, detail={"filename": filename})

    return FileResponse(
        path=str(backup_path),
        filename=filename,
        media_type="application/x-sqlite3",
    )


@router.post("/db/restore", status_code=status.HTTP_200_OK)
async def restore_database(
    file: UploadFile,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Ripristina il database da un file .db caricato.

    Prima di sovrascrivere, salva un backup automatico del DB corrente.
    """
    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="Il file deve avere estensione .db")

    # Salva il file caricato in una posizione temporanea
    _BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _BACKUPS_DIR / "restore_upload.tmp"
    content = await file.read()
    tmp_path.write_bytes(content)

    # Valida che sia un database SQLite valido
    try:
        conn = sqlite3.connect(str(tmp_path))
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
    except sqlite3.DatabaseError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Il file caricato non e' un database SQLite valido: {exc}",
        ) from exc

    # Audit prima della sostituzione (usa la sessione corrente)
    log_audit(
        db, "db_restore",
        user_id=admin.id,
        detail={"uploaded_filename": file.filename},
    )

    # Backup automatico del DB corrente prima di sovrascrivere
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    auto_backup_name = f"mubi_pre_restore_{ts}.db"
    auto_backup_path = _BACKUPS_DIR / auto_backup_name
    if _DB_PATH.exists():
        shutil.copy2(str(_DB_PATH), str(auto_backup_path))

    # Chiudi tutte le sessioni e il motore SQLAlchemy
    db.close()
    engine.dispose()

    # Sostituisci il database
    shutil.move(str(tmp_path), str(_DB_PATH))

    # Ricrea le connessioni SQLAlchemy
    Base.metadata.create_all(bind=engine)

    return {
        "message": "Database ripristinato con successo",
        "auto_backup": auto_backup_name,
    }


@router.get("/db/has-backups")
def has_backups(admin: User = Depends(require_admin)) -> dict:
    """Controlla se esistono backup precedenti nella cartella data/backups/."""
    if not _BACKUPS_DIR.exists():
        return {"has_backups": False, "files": []}
    files = sorted(
        [f.name for f in _BACKUPS_DIR.glob("*.db")],
        reverse=True,
    )
    return {"has_backups": len(files) > 0, "files": files[:10]}
