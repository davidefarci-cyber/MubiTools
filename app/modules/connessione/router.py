"""Router API per il modulo Connessione."""

import json
import logging
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
from app.modules.connessione.service import (
    estrai_pod_xml,
    genera_righe_connessione,
    genera_s01_massivo,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Store risultati in-memory (XML)
_xml_results: dict[str, dict] = {}

# Store risultati in-memory (S01 Massivo)
_s01_results: dict[str, dict] = {}

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
ALLOWED_XML_EXTENSIONS = {".xml"}
MAX_SIZE = settings.MAX_UPLOAD_MB * 1024 * 1024


# --- Schemas ---

class CreaRigaRequest(BaseModel):
    """Richiesta generazione righe connessione."""

    file_id: str


class CreaRigaResponse(BaseModel):
    """Risposta con righe generate per connessione."""

    rows_created: int
    columns: list[str]
    rows: list[list[str]]
    warnings: list[str]


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
    """Genera le righe per connessione dal file caricato.

    Restituisce le righe come dati JSON da visualizzare a schermo.
    """
    if not current_user.has_module("connessione"):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")

    source_path = _resolve_file(request.file_id)

    try:
        result = genera_righe_connessione(source_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Errore elaborazione connessione: %s", exc)
        raise HTTPException(status_code=500, detail=f"Errore elaborazione: {exc}") from exc

    log_audit(
        db, "connessione_crea_riga",
        user_id=current_user.id,
        detail={
            "file_id": request.file_id,
            "rows_created": result["rows_created"],
            "warnings_count": len(result["warnings"]),
        },
    )

    logger.info("Connessione: %d righe generate", result["rows_created"])

    return CreaRigaResponse(
        rows_created=result["rows_created"],
        columns=result["columns"],
        rows=result["rows"],
        warnings=result["warnings"],
    )


# ---------------------------------------------------------------------------
# XML POD Extractor endpoints
# ---------------------------------------------------------------------------


class EstraiPodRequest(BaseModel):
    """Richiesta estrazione POD da file XML."""

    file_id: str
    pods: list[str] = Field(min_length=1, max_length=500)


class EstraiPodResponse(BaseModel):
    """Risposta estrazione POD."""

    job_id: str
    found: list[str]
    not_found: list[str]
    total_requested: int
    download_ready: bool


@router.post("/xml/upload")
async def upload_xml_file(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Upload di un file XML per l'estrazione POD."""
    if not current_user.has_module("connessione"):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")

    original_name = file.filename or "unknown"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_XML_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Estensione '{ext}' non consentita. Ammessa: .xml",
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
        db, "connessione_xml_upload",
        user_id=current_user.id,
        detail={"file_id": file_id, "filename": original_name, "size": len(content)},
    )

    logger.info("Connessione XML upload: %s -> %s (%d bytes)", original_name, file_id, len(content))

    return {
        "file_id": file_id,
        "original_filename": original_name,
        "size_bytes": len(content),
    }


@router.post("/xml/estrai", response_model=EstraiPodResponse)
def process_estrai_pod(
    request: EstraiPodRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EstraiPodResponse:
    """Estrae blocchi DatiPod dal file XML caricato per i codici POD richiesti."""
    if not current_user.has_module("connessione"):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")

    source_path = _resolve_file(request.file_id)

    # Normalizza e deduplica la lista POD
    pods = list({p.strip() for p in request.pods if p.strip()})
    if not pods:
        raise HTTPException(status_code=400, detail="Nessun codice POD valido fornito")

    job_id = str(uuid.uuid4())

    try:
        result = estrai_pod_xml(source_path, pods, settings.UPLOAD_DIR)
    except Exception as exc:
        logger.exception("Errore estrazione XML job %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Errore elaborazione: {exc}") from exc

    _xml_results[job_id] = {
        "zip_path": result["zip_path"],
    }

    log_audit(
        db, "connessione_xml_estrai",
        user_id=current_user.id,
        detail={
            "job_id": job_id,
            "found": len(result["found"]),
            "not_found": len(result["not_found"]),
            "total_requested": result["total_requested"],
        },
    )

    logger.info(
        "Connessione XML job %s: %d trovati, %d non trovati",
        job_id, len(result["found"]), len(result["not_found"]),
    )

    return EstraiPodResponse(
        job_id=job_id,
        found=result["found"],
        not_found=result["not_found"],
        total_requested=result["total_requested"],
        download_ready=True,
    )


@router.get("/xml/download/{job_id}")
def download_xml_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download del file ZIP con i POD estratti."""
    if job_id not in _xml_results:
        raise HTTPException(status_code=404, detail="Risultato non trovato")

    zip_path = Path(_xml_results[job_id]["zip_path"])
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="File ZIP non trovato su disco")

    return FileResponse(
        path=zip_path,
        filename=f"pod_extract_{job_id}.zip",
        media_type="application/zip",
    )


# ---------------------------------------------------------------------------
# S01 Massivo endpoints
# ---------------------------------------------------------------------------


class S01MassivoRequest(BaseModel):
    """Richiesta generazione S01 Massivo."""

    file_id: str


class S01MassivoResponse(BaseModel):
    """Risposta generazione S01 Massivo."""

    job_id: str
    rows_created: int
    columns: list[str]
    rows_preview: list[list[str]]
    warnings: list[str]
    download_ready: bool


@router.post("/s01-massivo", response_model=S01MassivoResponse)
def process_s01_massivo(
    request: S01MassivoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> S01MassivoResponse:
    """Genera CSV + XLSX nel formato S01 Massivo dal file Excel caricato."""
    if not current_user.has_module("connessione"):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")

    source_path = _resolve_file(request.file_id)

    try:
        result = genera_s01_massivo(source_path, settings.UPLOAD_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Errore generazione S01 Massivo: %s", exc)
        raise HTTPException(status_code=500, detail=f"Errore elaborazione: {exc}") from exc

    _s01_results[result["job_id"]] = {
        "csv_path": result["csv_path"],
        "xlsx_path": result["xlsx_path"],
    }

    log_audit(
        db, "connessione_s01_massivo",
        user_id=current_user.id,
        detail={
            "file_id": request.file_id,
            "job_id": result["job_id"],
            "rows_created": result["rows_created"],
            "warnings_count": len(result["warnings"]),
        },
    )

    logger.info("S01 Massivo job %s: %d righe", result["job_id"], result["rows_created"])

    return S01MassivoResponse(
        job_id=result["job_id"],
        rows_created=result["rows_created"],
        columns=result["columns"],
        rows_preview=result["rows_preview"],
        warnings=result["warnings"],
        download_ready=True,
    )


@router.get("/s01-massivo/download/{job_id}/csv")
def download_s01_csv(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download del CSV S01 Massivo."""
    if job_id not in _s01_results:
        raise HTTPException(status_code=404, detail="Risultato non trovato")

    csv_path = Path(_s01_results[job_id]["csv_path"])
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="File CSV non trovato su disco")

    return FileResponse(
        path=csv_path,
        filename="S01_MASSIVO.csv",
        media_type="text/csv",
    )


@router.get("/s01-massivo/download/{job_id}/xlsx")
def download_s01_xlsx(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download del XLSX S01 Massivo."""
    if job_id not in _s01_results:
        raise HTTPException(status_code=404, detail="Risultato non trovato")

    xlsx_path = Path(_s01_results[job_id]["xlsx_path"])
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail="File XLSX non trovato su disco")

    return FileResponse(
        path=xlsx_path,
        filename="S01_MASSIVO.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
