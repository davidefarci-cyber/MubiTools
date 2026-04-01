"""Router API per il modulo Incassi Mubi."""

import json
import logging
import uuid
from pathlib import Path
from threading import Thread

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User, log_audit
from app.modules.incassi_mubi.schemas import ProcessRequest, ProcessResult, UploadResponse
from app.modules.incassi_mubi.service import elabora_incassi

logger = logging.getLogger(__name__)

router = APIRouter()

# Store dei job in-memory (adatto per singola istanza)
_jobs: dict[str, dict] = {}

ALLOWED_EXTENSIONS = {".txt", ".csv", ".xlsx", ".xls"}
MAX_SIZE = settings.MAX_UPLOAD_MB * 1024 * 1024


@router.get("/status")
def module_status(current_user: User = Depends(get_current_user)) -> dict:
    """Stato del modulo incassi."""
    return {"module": "incassi_mubi", "status": "active"}


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """Upload di un file per l'elaborazione.

    Valida estensione e dimensione, salva con UUID come nome.
    """
    if not current_user.has_module("incassi_mubi"):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")

    # Validazione estensione
    original_name = file.filename or "unknown"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Estensione '{ext}' non consentita. Ammesse: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Leggi contenuto e valida dimensione
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File troppo grande ({len(content) // (1024*1024)}MB). Max: {settings.MAX_UPLOAD_MB}MB",
        )

    # Salva con UUID
    file_id = str(uuid.uuid4())
    save_path = settings.UPLOAD_DIR / f"{file_id}{ext}"
    save_path.write_bytes(content)

    # Salva mapping file_id -> nome originale
    meta_path = settings.UPLOAD_DIR / f"{file_id}.meta"
    meta_path.write_text(json.dumps({
        "original_filename": original_name,
        "extension": ext,
        "size_bytes": len(content),
    }))

    log_audit(
        db, "incassi_upload",
        user_id=current_user.id,
        detail={"file_id": file_id, "filename": original_name, "size": len(content)},
    )

    logger.info("File upload: %s -> %s (%d bytes)", original_name, file_id, len(content))

    return UploadResponse(
        file_id=file_id,
        original_filename=original_name,
        size_bytes=len(content),
    )


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


def _run_elaborazione(job_id: str, request: ProcessRequest, user_id: int) -> None:
    """Esegue l'elaborazione in un thread separato."""
    job = _jobs[job_id]

    try:
        file_incassi = _resolve_file(request.file_incassi_id)
        file_massivo = _resolve_file(request.file_massivo_id)
        file_conferimento = _resolve_file(request.file_conferimento_id)
        file_piani = _resolve_file(request.file_piani_rientro_id) if request.file_piani_rientro_id else None

        output_dir = settings.UPLOAD_DIR / f"output_{job_id}"

        def on_progress(phase: int, message: str) -> None:
            job["current_phase"] = phase
            job["phases"][phase - 1]["status"] = "running"
            job["phases"][phase - 1]["message"] = message
            # Segna fasi precedenti come completate
            for i in range(phase - 1):
                if job["phases"][i]["status"] == "running":
                    job["phases"][i]["status"] = "completed"

        results = elabora_incassi(
            file_incassi=file_incassi,
            file_massivo=file_massivo,
            file_conferimento=file_conferimento,
            file_piani=file_piani,
            output_dir=output_dir,
            progress_callback=on_progress,
        )

        # Segna tutte le fasi come completate
        for p in job["phases"]:
            p["status"] = "completed"

        job["status"] = "completed"
        job["total_fatture"] = results["total_fatture"]
        job["fatture_incassate"] = results["fatture_incassate"]
        job["anomalie"] = results["anomalie"]
        job["piani_rientro"] = results["piani_rientro"]
        job["nuove_righe"] = results["nuove_righe"]
        job["message"] = results.get("pivot_message", "Elaborazione completata")
        job["download_ready"] = True
        job["output_dir"] = str(output_dir)
        job["anomalie_detail"] = results.get("anomalie_detail", [])
        job["correzioni_detail"] = results.get("correzioni_detail", [])
        job["files"] = results.get("files", {})

        logger.info("Job %s completato: %d fatture", job_id, results["total_fatture"])

    except Exception as e:
        logger.exception("Job %s fallito: %s", job_id, e)
        job["status"] = "error"
        job["message"] = str(e)
        # Segna la fase corrente come errore
        current = job.get("current_phase", 1)
        if current > 0 and current <= len(job["phases"]):
            job["phases"][current - 1]["status"] = "error"
            job["phases"][current - 1]["message"] = str(e)


@router.post("/process", response_model=ProcessResult)
def start_processing(
    request: ProcessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProcessResult:
    """Avvia l'elaborazione con i file caricati."""
    if not current_user.has_module("incassi_mubi"):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")

    job_id = str(uuid.uuid4())
    phase_names = [
        "Conversione file Incassi",
        "Cerca.Vert Importo Aperto",
        "Piani di Rientro",
        "Popola Conferimento",
        "Confronto Identico",
        "Ordinamento e Controllo",
        "Aggiornamento Pivot",
    ]

    _jobs[job_id] = {
        "status": "processing",
        "current_phase": 0,
        "phases": [
            {"phase": i + 1, "name": name, "status": "pending", "message": ""}
            for i, name in enumerate(phase_names)
        ],
        "total_fatture": 0,
        "fatture_incassate": 0,
        "anomalie": 0,
        "piani_rientro": 0,
        "nuove_righe": 0,
        "message": "Elaborazione avviata",
        "download_ready": False,
    }

    log_audit(
        db, "incassi_process_start",
        user_id=current_user.id,
        detail={"job_id": job_id},
    )

    # Esegui in thread separato
    thread = Thread(
        target=_run_elaborazione,
        args=(job_id, request, current_user.id),
        daemon=True,
    )
    thread.start()

    return ProcessResult(
        job_id=job_id,
        status="processing",
        message="Elaborazione avviata",
        phases=[
            {"phase": p["phase"], "name": p["name"], "status": p["status"], "message": p["message"]}
            for p in _jobs[job_id]["phases"]
        ],
    )


@router.get("/result/{job_id}", response_model=ProcessResult)
def get_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> ProcessResult:
    """Stato elaborazione e risultati."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job non trovato")

    job = _jobs[job_id]
    return ProcessResult(
        job_id=job_id,
        status=job["status"],
        current_phase=job.get("current_phase", 0),
        phases=[
            {"phase": p["phase"], "name": p["name"], "status": p["status"], "message": p["message"]}
            for p in job["phases"]
        ],
        total_fatture=job.get("total_fatture", 0),
        fatture_incassate=job.get("fatture_incassate", 0),
        anomalie=job.get("anomalie", 0),
        piani_rientro=job.get("piani_rientro", 0),
        nuove_righe=job.get("nuove_righe", 0),
        message=job.get("message", ""),
        download_ready=job.get("download_ready", False),
    )


@router.get("/result/{job_id}/anomalie")
def get_anomalie(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Dettaglio anomalie per un job completato."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job non trovato")
    job = _jobs[job_id]
    return {
        "anomalie": job.get("anomalie_detail", []),
        "correzioni": job.get("correzioni_detail", []),
    }


@router.get("/download/{job_id}/{file_type}")
def download_file(
    job_id: str,
    file_type: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download file output (conferimento, anomalie, nuove_righe)."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job non trovato")

    job = _jobs[job_id]
    if not job.get("download_ready"):
        raise HTTPException(status_code=400, detail="Elaborazione non ancora completata")

    files = job.get("files", {})
    file_path_str = files.get(file_type)
    if not file_path_str:
        raise HTTPException(status_code=404, detail=f"File '{file_type}' non disponibile")

    file_path = Path(file_path_str)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File non trovato su disco")

    filename_map = {
        "conferimento": "conferimento_aggiornato.xlsx",
        "anomalie": "report_anomalie.xlsx",
        "nuove_righe": "nuove_righe_conferimento.xlsx",
    }

    return FileResponse(
        path=file_path,
        filename=filename_map.get(file_type, file_path.name),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
