"""Router modulo Invio REMI: impostazioni, template, pending, invio massivo, anagrafica DL."""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.auth.dependencies import get_current_user, require_module
from app.database import get_db
from app.models import User
from app.modules.invio_remi import service, settings_service
from app.modules.invio_remi.schemas import (
    DlRegistryBulkResponse,
    DlRegistryBulkRow,
    DlRegistryCreate,
    DlRegistryOut,
    DlRegistryUpdate,
)
from app.admin import pec_service

logger = logging.getLogger(__name__)

router = APIRouter()

MODULE_NAME = "invio_remi"


@router.get("/pec")
def list_active_pec(
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Lista PEC attive per la selezione nelle impostazioni di invio REMI.

    Endpoint dedicato al modulo (non admin): restituisce solo i campi
    necessari al dropdown (id, label, email), filtra a is_active=True.
    """
    return [
        {"id": p.id, "label": p.label, "email": p.email}
        for p in pec_service.list_pec_accounts(db)
        if p.is_active
    ]


@router.get("/settings")
def get_settings(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Restituisce le impostazioni correnti di invio REMI + info template DOCX."""
    data = settings_service.load_settings()
    data["docx_template_present"] = settings_service.template_exists()
    return data


@router.post("/settings")
async def save_settings(
    pec_account_id: int | None = Form(None),
    subject: str = Form(""),
    body_template: str = Form(""),
    docx_template: UploadFile | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Salva le impostazioni di invio REMI (multipart: campi + file DOCX opzionale)."""
    docx_content = await docx_template.read() if docx_template and docx_template.filename else None
    docx_filename = docx_template.filename if docx_template and docx_template.filename else None
    return await service.save_settings_with_template(
        db,
        current_user.id,
        pec_account_id=pec_account_id,
        subject=subject,
        body_template=body_template,
        docx_template_filename=docx_filename,
        docx_template_content=docx_content,
    )


@router.get("/settings/template")
def download_template(
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download del file DOCX template corrente."""
    if not settings_service.template_exists():
        raise HTTPException(status_code=404, detail="Nessun template DOCX configurato")

    settings_data = settings_service.load_settings()
    filename = settings_data.get("docx_template_filename") or "remi_template.docx"

    return FileResponse(
        path=str(settings_service.get_template_path()),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# --- Sincronizzazione PEC da anagrafica ---


@router.post("/sync-registry")
def sync_pending_from_registry(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Aggiorna PEC e ragione sociale delle pratiche pending dall'anagrafica DL."""
    return service.sync_pending_from_registry(db, current_user.id)


# --- Pratiche pending aggregate per distributore ---


@router.get("/pending")
def get_pending_practices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Restituisce le pratiche pending aggregate per distributore (vat_number)."""
    return service.list_pending_grouped(db)


# --- Invio massivo con SSE ---


@router.post("/send-all")
async def send_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Avvia l'invio massivo PEC per tutte le pratiche pending (risposta SSE)."""
    return StreamingResponse(
        service.stream_send_all(db, current_user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Anagrafica Distributori Locali ---


@router.get("/registry", response_model=list[DlRegistryOut])
def list_registry(
    search: str | None = None,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> list[DlRegistryOut]:
    """Lista distributori locali con filtro testo opzionale."""
    return service.list_registry(db, search)


@router.post("/registry", response_model=DlRegistryOut, status_code=201)
def create_registry(
    data: DlRegistryCreate,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> DlRegistryOut:
    """Crea un nuovo distributore locale."""
    return service.create_registry(db, data, current_user.id, current_user.username)


@router.put("/registry/{dl_id}", response_model=DlRegistryOut)
def update_registry(
    dl_id: int,
    data: DlRegistryUpdate,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> DlRegistryOut:
    """Modifica un distributore locale esistente."""
    return service.update_registry(db, dl_id, data, current_user.id, current_user.username)


@router.delete("/registry/{dl_id}")
def deactivate_registry(
    dl_id: int,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> dict:
    """Disattiva un distributore locale (soft delete)."""
    return service.deactivate_registry(db, dl_id, current_user.id, current_user.username)


@router.put("/registry/{dl_id}/reactivate", response_model=DlRegistryOut)
def reactivate_registry(
    dl_id: int,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> DlRegistryOut:
    """Riattiva un distributore locale precedentemente disattivato."""
    return service.reactivate_registry(db, dl_id, current_user.id, current_user.username)


@router.post("/registry/bulk", response_model=DlRegistryBulkResponse)
def bulk_create_registry(
    rows: list[DlRegistryBulkRow],
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> DlRegistryBulkResponse:
    """Caricamento massivo distributori locali da incolla Excel."""
    return service.bulk_create_registry(db, rows, current_user.id, current_user.username)
