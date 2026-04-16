"""Router modulo Invio REMI: impostazioni, template, pending, invio massivo."""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import RemiPractice, User, log_audit
from app.modules.invio_remi import email_service, settings_service
from app.modules.invio_remi.pdf_service import format_date_for_display, generate_pdf

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


# --- Pratiche pending aggregate per distributore ---


@router.get("/pending")
def get_pending_practices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Restituisce le pratiche pending aggregate per distributore (vat_number)."""
    practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.status == "pending")
        .order_by(RemiPractice.vat_number, RemiPractice.id)
        .all()
    )

    # Aggrega per vat_number
    groups: dict[str, dict] = {}
    for p in practices:
        key = p.vat_number
        if key not in groups:
            groups[key] = {
                "vat_number": p.vat_number,
                "company_name": p.company_name,
                "pec_address": p.pec_address,
                "effective_date": p.effective_date.isoformat() if p.effective_date else None,
                "remi_codes": [],
                "practice_ids": [],
                "practice_count": 0,
            }
        groups[key]["remi_codes"].append(p.remi_code)
        groups[key]["practice_ids"].append(p.id)
        groups[key]["practice_count"] += 1

    return list(groups.values())


# --- Invio massivo con SSE ---


@router.post("/send-all")
async def send_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Avvia l'invio massivo PEC per tutte le pratiche pending.

    Restituisce aggiornamenti in streaming SSE.
    """
    # Carica impostazioni e valida completezza
    settings_data = settings_service.load_settings()
    pec_account_id = settings_data.get("pec_account_id")
    subject = settings_data.get("subject", "")
    body_template = settings_data.get("body_template", "")

    if not pec_account_id:
        raise HTTPException(status_code=400, detail="Account PEC non configurato nelle impostazioni")
    if not subject:
        raise HTTPException(status_code=400, detail="Oggetto PEC non configurato nelle impostazioni")
    if not body_template:
        raise HTTPException(status_code=400, detail="Testo PEC non configurato nelle impostazioni")
    if not settings_service.template_exists():
        raise HTTPException(status_code=400, detail="Template DOCX non caricato")

    # Carica pratiche pending aggregate
    practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.status == "pending")
        .order_by(RemiPractice.vat_number, RemiPractice.id)
        .all()
    )

    if not practices:
        raise HTTPException(status_code=400, detail="Nessuna pratica in attesa di invio")

    # Aggrega per vat_number
    groups: dict[str, list[RemiPractice]] = {}
    for p in practices:
        groups.setdefault(p.vat_number, []).append(p)

    send_batch_id = str(uuid.uuid4())
    user_id = current_user.id

    async def event_stream():
        sent_count = 0
        error_count = 0

        for vat_number, dl_practices in groups.items():
            first = dl_practices[0]
            company_name = first.company_name
            pec_address = first.pec_address
            effective_date = first.effective_date.isoformat() if first.effective_date else ""
            remi_codes = [p.remi_code for p in dl_practices]

            # Stato: generazione PDF
            yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'generating_pdf'})}\n\n"

            try:
                file_bytes, file_format = await generate_pdf(
                    company_name=company_name,
                    pec_address=pec_address,
                    effective_date=effective_date,
                    remi_codes=remi_codes,
                )
            except Exception as exc:
                error_msg = str(exc)
                logger.exception("Errore generazione documento per DL %s", vat_number)
                # Aggiorna stato pratiche
                for p in dl_practices:
                    p.status = "error"
                    p.error_detail = f"Errore generazione PDF: {error_msg}"
                    p.send_batch_id = send_batch_id
                db.commit()
                error_count += 1
                yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'error', 'error': error_msg})}\n\n"
                continue

            # Stato: invio PEC
            yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'sending'})}\n\n"

            try:
                # Costruisci corpo PEC con sostituzione tag
                formatted_date = format_date_for_display(effective_date)
                body = body_template
                body = body.replace("<REMI>", ", ".join(remi_codes))
                body = body.replace("<NOME_DL>", company_name)
                body = body.replace("<PEC_DL>", pec_address)
                body = body.replace("<DATA_DECORRENZA>", formatted_date)

                file_ext = "pdf" if file_format == "pdf" else "docx"
                attachment_filename = f"REMI_{vat_number}.{file_ext}"

                result = await email_service.send_pec(
                    pec_account_id=pec_account_id,
                    to_address=pec_address,
                    subject=subject,
                    body=body,
                    attachment=file_bytes,
                    attachment_filename=attachment_filename,
                    db=db,
                )

                now = datetime.now(timezone.utc)

                if result.get("success"):
                    for p in dl_practices:
                        p.status = "sent"
                        p.sent_at = now
                        p.send_batch_id = send_batch_id
                    db.commit()
                    sent_count += 1
                    yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'sent'})}\n\n"
                else:
                    error_msg = result.get("error", "Errore sconosciuto")
                    for p in dl_practices:
                        p.status = "error"
                        p.error_detail = error_msg
                        p.send_batch_id = send_batch_id
                    db.commit()
                    error_count += 1
                    yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'error', 'error': error_msg})}\n\n"

            except Exception as exc:
                error_msg = str(exc)
                logger.exception("Errore invio PEC per DL %s", vat_number)
                for p in dl_practices:
                    p.status = "error"
                    p.error_detail = f"Errore invio: {error_msg}"
                    p.send_batch_id = send_batch_id
                db.commit()
                error_count += 1
                yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'error', 'error': error_msg})}\n\n"

        # Audit log
        log_audit(
            db, "remi_send_all",
            user_id=user_id,
            detail={
                "send_batch_id": send_batch_id,
                "sent": sent_count,
                "errors": error_count,
                "total_dl": len(groups),
            },
        )

        # Evento finale
        yield f"data: {json.dumps({'type': 'complete', 'sent': sent_count, 'errors': error_count})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
