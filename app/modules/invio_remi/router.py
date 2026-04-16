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
from app.database import SessionLocal, get_db
from app.models import DlRegistry, RemiPractice, User, log_audit
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


# --- Sincronizzazione PEC da anagrafica ---


@router.post("/sync-registry")
def sync_pending_from_registry(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Aggiorna PEC e ragione sociale delle pratiche pending dall'anagrafica DL."""
    pending = (
        db.query(RemiPractice)
        .filter(RemiPractice.status == "pending")
        .all()
    )

    if not pending:
        return {"updated": 0, "message": "Nessuna pratica in attesa"}

    # Carica anagrafica corrente indicizzata per P.IVA
    registry_entries = db.query(DlRegistry).filter(DlRegistry.is_active == True).all()
    registry_map = {dl.vat_number: dl for dl in registry_entries}

    updated_count = 0
    for p in pending:
        dl = registry_map.get(p.vat_number)
        if not dl:
            continue
        changed = False
        if p.pec_address != dl.pec_address:
            p.pec_address = dl.pec_address
            changed = True
        if p.company_name != dl.company_name:
            p.company_name = dl.company_name
            changed = True
        if changed:
            updated_count += 1

    if updated_count > 0:
        db.commit()
        log_audit(
            db, "remi_sync_registry",
            user_id=current_user.id,
            detail={"updated": updated_count, "total_pending": len(pending)},
        )

    return {"updated": updated_count, "total_pending": len(pending)}


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

    # Prepara dati serializzati per il generatore (NO oggetti ORM che
    # diventerebbero detached dopo la chiusura della sessione Depends).
    groups_data: dict[str, dict] = {}
    for p in practices:
        key = p.vat_number
        if key not in groups_data:
            groups_data[key] = {
                "vat_number": p.vat_number,
                "company_name": p.company_name,
                "pec_address": p.pec_address,
                "effective_date": p.effective_date.isoformat() if p.effective_date else "",
                "remi_codes": [],
                "practice_ids": [],
            }
        groups_data[key]["remi_codes"].append(p.remi_code)
        groups_data[key]["practice_ids"].append(p.id)

    send_batch_id = str(uuid.uuid4())
    user_id = current_user.id

    async def event_stream():
        # Sessione indipendente: la sessione da Depends viene chiusa quando
        # l'endpoint ritorna la StreamingResponse, prima che il generatore
        # inizi ad eseguire.  Usando SessionLocal() il ciclo di vita è
        # controllato interamente dal generatore.
        gen_db = SessionLocal()
        sent_count = 0
        error_count = 0

        try:
            for vat_number, group_info in groups_data.items():
                company_name = group_info["company_name"]
                pec_address = group_info["pec_address"]
                effective_date = group_info["effective_date"]
                remi_codes = group_info["remi_codes"]
                practice_ids = group_info["practice_ids"]

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
                    dl_practices = (
                        gen_db.query(RemiPractice)
                        .filter(RemiPractice.id.in_(practice_ids))
                        .all()
                    )
                    for p in dl_practices:
                        p.status = "error"
                        p.error_detail = f"Errore generazione PDF: {error_msg}"
                        p.send_batch_id = send_batch_id
                    gen_db.commit()
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
                        db=gen_db,
                    )

                    now = datetime.now(timezone.utc)

                    dl_practices = (
                        gen_db.query(RemiPractice)
                        .filter(RemiPractice.id.in_(practice_ids))
                        .all()
                    )

                    if result.get("success"):
                        for p in dl_practices:
                            p.status = "sent"
                            p.sent_at = now
                            p.send_batch_id = send_batch_id
                        gen_db.commit()
                        sent_count += 1
                        yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'sent'})}\n\n"
                    else:
                        error_msg = result.get("error", "Errore sconosciuto")
                        for p in dl_practices:
                            p.status = "error"
                            p.error_detail = error_msg
                            p.send_batch_id = send_batch_id
                        gen_db.commit()
                        error_count += 1
                        yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'error', 'error': error_msg})}\n\n"

                except Exception as exc:
                    error_msg = str(exc)
                    logger.exception("Errore invio PEC per DL %s", vat_number)
                    dl_practices = (
                        gen_db.query(RemiPractice)
                        .filter(RemiPractice.id.in_(practice_ids))
                        .all()
                    )
                    for p in dl_practices:
                        p.status = "error"
                        p.error_detail = f"Errore invio: {error_msg}"
                        p.send_batch_id = send_batch_id
                    gen_db.commit()
                    error_count += 1
                    yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'error', 'error': error_msg})}\n\n"

            # Audit log
            log_audit(
                gen_db, "remi_send_all",
                user_id=user_id,
                detail={
                    "send_batch_id": send_batch_id,
                    "sent": sent_count,
                    "errors": error_count,
                    "total_dl": len(groups_data),
                },
            )

            # Evento finale
            yield f"data: {json.dumps({'type': 'complete', 'sent': sent_count, 'errors': error_count})}\n\n"
        finally:
            gen_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
