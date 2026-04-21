"""Router pannello admin: orchestrazione thin (auth + parsing + delega)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.admin import backup_service, pec_service
from app.admin import service as admin_service
from app.admin import update_service
from app.admin.schemas import (
    ApplyUpdateRequest,
    AuditLogOut,
    CreatePecRequest,
    CreateUserRequest,
    ResetPasswordRequest,
    UpdatePecRequest,
    UpdateUserRequest,
    UserOut,
)
from app.auth.dependencies import require_admin
from app.database import get_db
from app.models import PecAccount, User, log_audit

logger = logging.getLogger(__name__)

router = APIRouter()


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


def _pec_to_dict(pec: PecAccount) -> dict:
    """Converte un PecAccount ORM in dict per la risposta (senza password)."""
    return {
        "id": pec.id,
        "label": pec.label,
        "email": pec.email,
        "username": pec.username,
        "is_active": pec.is_active,
        "created_at": pec.created_at.isoformat() if pec.created_at else None,
    }


# --- Users ---

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
    if admin_service.get_user_by_username(db, request.username):
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


# --- Audit log ---

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


@router.delete("/audit-log")
def clear_audit_log(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Cancella tutte le voci dell'audit log e registra l'operazione."""
    deleted = admin_service.delete_audit_log(db, deleted_by_id=admin.id)
    return {"deleted": deleted}


# --- PEC Accounts ---

@router.get("/pec")
def list_pec(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Lista tutte le connessioni PEC configurate (password esclusa)."""
    return [_pec_to_dict(p) for p in pec_service.list_pec_accounts(db)]


@router.post("/pec", status_code=status.HTTP_201_CREATED)
def create_pec(
    request: CreatePecRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Crea una nuova connessione PEC."""
    try:
        pec = pec_service.create_pec(
            db,
            label=request.label,
            email=request.email,
            username=request.username,
            password=request.password,
            created_by_id=admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _pec_to_dict(pec)


@router.put("/pec/{pec_id}")
def update_pec(
    pec_id: int,
    request: UpdatePecRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Modifica una connessione PEC. Se password e' vuota/null, non viene aggiornata."""
    pec = pec_service.get_pec_by_id(db, pec_id)
    if not pec:
        raise HTTPException(status_code=404, detail="Connessione PEC non trovata")
    try:
        pec = pec_service.update_pec(
            db,
            pec=pec,
            label=request.label,
            email=request.email,
            username=request.username,
            password=request.password,
            is_active=request.is_active,
            updated_by_id=admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _pec_to_dict(pec)


@router.delete("/pec/{pec_id}")
def delete_pec(
    pec_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Elimina una connessione PEC (non se e' l'unica attiva)."""
    pec = pec_service.get_pec_by_id(db, pec_id)
    if not pec:
        raise HTTPException(status_code=404, detail="Connessione PEC non trovata")
    try:
        pec_service.delete_pec(db, pec=pec, deleted_by_id=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Connessione PEC eliminata"}


@router.post("/pec/{pec_id}/test")
def test_pec(
    pec_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Testa la connessione SMTP di un account PEC (login senza invio mail)."""
    pec = pec_service.get_pec_by_id(db, pec_id)
    if not pec:
        raise HTTPException(status_code=404, detail="Connessione PEC non trovata")

    success, error = pec_service.test_pec_smtp(pec)
    if success:
        log_audit(db, "pec_test_ok", user_id=admin.id,
                  detail={"pec_id": pec.id, "email": pec.email})
        return {"success": True}

    log_audit(db, "pec_test_fail", user_id=admin.id,
              detail={"pec_id": pec.id, "email": pec.email, "error": error})
    return {"success": False, "error": error}


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

@router.get("/db/backup")
def backup_database(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Scarica un backup del database SQLite corrente."""
    try:
        backup_path, filename = backup_service.create_backup(db, created_by_id=admin.id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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

    content = await file.read()
    try:
        auto_backup_name = backup_service.restore_database(
            db,
            uploaded_filename=file.filename,
            content=content,
            restored_by_id=admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Database ripristinato con successo",
        "auto_backup": auto_backup_name,
    }


@router.post("/db/reinit")
def reinit_database(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Elimina e ricrea tutte le tabelle del database (reset completo)."""
    db.close()
    auto_backup_name = backup_service.reinit_database(triggered_by_username=admin.username)
    return {
        "message": "Database reinizializzato con successo",
        "auto_backup": auto_backup_name,
    }


@router.get("/db/has-backups")
def has_backups(admin: User = Depends(require_admin)) -> dict:
    """Controlla se esistono backup precedenti nella cartella data/backups/."""
    files = backup_service.list_recent_backups(limit=10)
    return {"has_backups": len(files) > 0, "files": files}
