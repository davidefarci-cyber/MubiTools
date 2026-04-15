"""Router modulo Invio REMI: impostazioni e template."""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import User, log_audit
from app.modules.invio_remi import settings_service

logger = logging.getLogger(__name__)

router = APIRouter()


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
    settings_data = settings_service.load_settings()
    settings_data["pec_account_id"] = pec_account_id
    settings_data["subject"] = subject
    settings_data["body_template"] = body_template

    # Salva il file DOCX template se fornito
    if docx_template and docx_template.filename:
        if not docx_template.filename.lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="Il template deve essere un file .docx")
        content = await docx_template.read()
        settings_service.save_template(content)
        settings_data["docx_template_filename"] = docx_template.filename
        logger.info("Template DOCX salvato: %s", docx_template.filename)

    settings_service.save_settings(settings_data)
    log_audit(db, "remi_settings_updated", user_id=current_user.id)

    return {"message": "Impostazioni salvate", "settings": settings_data}


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
