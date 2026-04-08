"""Router API per il modulo Connessione."""

import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User, log_audit
from app.modules.connessione.service import crea_riga_file_a

logger = logging.getLogger(__name__)

router = APIRouter()

# Store risultati in-memory
_results: dict[str, dict] = {}

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
MAX_SIZE = settings.MAX_UPLOAD_MB * 1024 * 1024


# --- Schemas ---

class CreaRigaRequest(BaseModel):
    """Richiesta creazione riga FILE A."""

    file_id: str
    sheet_name: str = Field(default="Riga FILE A", min_length=1, max_length=100)


class CreaRigaResponse(BaseModel):
    """Risposta creazione riga FILE A."""

    job_id: str
    rows_created: int
    warnings: list[str]
    download_ready: bool


# --- Endpoints ---

@router.get("/status")
def module_status(current_user: User = Depends(get_current_user)) -> dict:
    """Stato del modulo connessione."""
    return {"module": "connessione", "status": "active"}


@router.post("/upload")
async def upload_file(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Upload di un file Excel per l'elaborazione."""
    if not current_user.has_module("connessione"):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")

    original_name = file.filename or "unknown"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Estensione '{ext}' non consentita. Ammesse: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File troppo grande ({len(content) // (1024*1024)}MB). Max: {settings.MAX_UPLOAD_MB}MB",
        )

    file_id = str(uuid.uuid4())
    save_path = settings.UPLOAD_DIR / f"{file_id}{ext}"
    save_path.write_bytes(content)

    meta_path = settings.UPLOAD_DIR / f"{file_id}.meta"
    meta_path.write_text(json.dumps({
        "original_filename": original_name,
        "extension": ext,
        "size_bytes": len(content),
    }))

    log_audit(
        db, "connessione_upload",
        user_id=current_user.id,
        detail={"file_id": file_id, "filename": original_name, "size": len(content)},
    )

    logger.info("Connessione upload: %s -> %s (%d bytes)", original_name, file_id, len(content))

    return {
        "file_id": file_id,
        "original_filename": original_name,
        "size_bytes": len(content),
    }


def _resolve_file(file_id: str) -> Path:
    """Risolve un file_id in un percorso reale."""
    meta_path = settings.UPLOAD_DIR / f"{file_id}.meta"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{file_id}' non trovato")
    meta = json.loads(meta_path.read_text())
    file_path = settings.UPLOAD_DIR / f"{file_id}{meta['extension']}"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{file_id}' non trovato su disco")
    return file_path


@router.post("/crea-riga", response_model=CreaRigaResponse)
def process_crea_riga(
    request: CreaRigaRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreaRigaResponse:
    """Crea le righe FILE A dal FILE B caricato.

    Elaborazione sincrona: mappa colonne, trasforma valori, scrive foglio.
    """
    if not current_user.has_module("connessione"):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")

    source_path = _resolve_file(request.file_id)
    job_id = str(uuid.uuid4())

    # Crea copia di lavoro per non modificare l'originale upload
    work_path = settings.UPLOAD_DIR / f"conn_output_{job_id}{source_path.suffix}"
    shutil.copy2(source_path, work_path)

    try:
        result = crea_riga_file_a(work_path, request.sheet_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Errore elaborazione connessione job %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Errore elaborazione: {exc}") from exc

    # Recupera nome originale per il download
    meta_path = settings.UPLOAD_DIR / f"{request.file_id}.meta"
    meta = json.loads(meta_path.read_text())

    _results[job_id] = {
        "output_path": str(work_path),
        "original_filename": meta["original_filename"],
        "rows_created": result["rows_created"],
        "warnings": result["warnings"],
    }

    log_audit(
        db, "connessione_crea_riga",
        user_id=current_user.id,
        detail={
            "job_id": job_id,
            "rows_created": result["rows_created"],
            "warnings_count": len(result["warnings"]),
        },
    )

    logger.info("Connessione job %s: %d righe create", job_id, result["rows_created"])

    return CreaRigaResponse(
        job_id=job_id,
        rows_created=result["rows_created"],
        warnings=result["warnings"],
        download_ready=True,
    )


@router.get("/download/{job_id}")
def download_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download del file risultato con il foglio FILE A aggiunto."""
    if job_id not in _results:
        raise HTTPException(status_code=404, detail="Risultato non trovato")

    info = _results[job_id]
    file_path = Path(info["output_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File non trovato su disco")

    return FileResponse(
        path=file_path,
        filename=info["original_filename"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
