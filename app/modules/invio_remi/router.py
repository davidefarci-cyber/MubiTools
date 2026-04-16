"""Router modulo Invio REMI: impostazioni, template, pending, invio massivo, anagrafica DL."""

import json
import logging
import re
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
from app.modules.caricamento_remi.service import validate_partita_iva
from app.modules.invio_remi import email_service, settings_service
from app.modules.invio_remi.pdf_service import format_date_for_display, generate_pdf
from app.modules.invio_remi.schemas import (
    DlRegistryBulkResponse,
    DlRegistryBulkResultRow,
    DlRegistryBulkRow,
    DlRegistryCreate,
    DlRegistryOut,
    DlRegistryUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MODULE_NAME = "invio_remi"

# Regex per validazione formato email/PEC
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _require_module(user: User) -> None:
    """Verifica che l'utente abbia accesso al modulo."""
    if not user.has_module(MODULE_NAME):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")


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
                    file_bytes = await generate_pdf(
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
                    body = body.replace("<DATA>", datetime.now().strftime("%d/%m/%Y"))

                    attachment_filename = f"REMI_{vat_number}.pdf"

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


# --- Anagrafica Distributori Locali ---


@router.get("/registry", response_model=list[DlRegistryOut])
def list_registry(
    search: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DlRegistryOut]:
    """Lista distributori locali con filtro testo opzionale."""
    _require_module(current_user)

    query = db.query(DlRegistry)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            DlRegistry.company_name.ilike(pattern)
            | DlRegistry.vat_number.ilike(pattern)
            | DlRegistry.pec_address.ilike(pattern)
        )
    query = query.order_by(DlRegistry.company_name)
    return query.all()


@router.post("/registry", response_model=DlRegistryOut, status_code=201)
def create_registry(
    data: DlRegistryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DlRegistryOut:
    """Crea un nuovo distributore locale."""
    _require_module(current_user)

    if not validate_partita_iva(data.vat_number):
        raise HTTPException(status_code=400, detail="Partita IVA non valida")

    if not _EMAIL_RE.match(data.pec_address):
        raise HTTPException(status_code=400, detail="Formato PEC non valido")

    existing = db.query(DlRegistry).filter(DlRegistry.vat_number == data.vat_number).first()
    if existing:
        raise HTTPException(status_code=409, detail="Partita IVA già registrata")

    dl = DlRegistry(
        company_name=data.company_name.strip(),
        vat_number=data.vat_number.strip(),
        pec_address=data.pec_address.strip(),
        is_active=True,
    )
    db.add(dl)
    db.commit()
    db.refresh(dl)

    log_audit(
        db,
        "dl_registry_created",
        user_id=current_user.id,
        detail={
            "dl_id": dl.id,
            "company_name": dl.company_name,
            "vat_number": dl.vat_number,
        },
    )

    logger.info("DL creato: %s (P.IVA %s) da %s", dl.company_name, dl.vat_number, current_user.username)
    return dl


@router.put("/registry/{dl_id}", response_model=DlRegistryOut)
def update_registry(
    dl_id: int,
    data: DlRegistryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DlRegistryOut:
    """Modifica un distributore locale esistente."""
    _require_module(current_user)

    dl = db.query(DlRegistry).filter(DlRegistry.id == dl_id).first()
    if not dl:
        raise HTTPException(status_code=404, detail="Distributore non trovato")

    if data.vat_number is not None:
        if not validate_partita_iva(data.vat_number):
            raise HTTPException(status_code=400, detail="Partita IVA non valida")
        existing = (
            db.query(DlRegistry)
            .filter(DlRegistry.vat_number == data.vat_number, DlRegistry.id != dl_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="Partita IVA già registrata")
        dl.vat_number = data.vat_number.strip()

    if data.pec_address is not None:
        if not _EMAIL_RE.match(data.pec_address):
            raise HTTPException(status_code=400, detail="Formato PEC non valido")
        dl.pec_address = data.pec_address.strip()

    if data.company_name is not None:
        dl.company_name = data.company_name.strip()

    dl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dl)

    log_audit(
        db,
        "dl_registry_updated",
        user_id=current_user.id,
        detail={"dl_id": dl.id, "company_name": dl.company_name, "vat_number": dl.vat_number},
    )

    logger.info("DL aggiornato: id=%d da %s", dl.id, current_user.username)
    return dl


@router.delete("/registry/{dl_id}")
def deactivate_registry(
    dl_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Disattiva un distributore locale (soft delete)."""
    _require_module(current_user)

    dl = db.query(DlRegistry).filter(DlRegistry.id == dl_id).first()
    if not dl:
        raise HTTPException(status_code=404, detail="Distributore non trovato")

    if not dl.is_active:
        raise HTTPException(status_code=400, detail="Distributore già disattivato")

    pending_count = (
        db.query(RemiPractice)
        .filter(RemiPractice.vat_number == dl.vat_number, RemiPractice.status == "pending")
        .count()
    )
    if pending_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Impossibile disattivare: {pending_count} pratiche in stato pending associate a questa P.IVA",
        )

    dl.is_active = False
    dl.updated_at = datetime.now(timezone.utc)
    db.commit()

    log_audit(
        db,
        "dl_registry_deactivated",
        user_id=current_user.id,
        detail={"dl_id": dl.id, "company_name": dl.company_name, "vat_number": dl.vat_number},
    )

    logger.info("DL disattivato: id=%d da %s", dl.id, current_user.username)
    return {"detail": "Distributore disattivato"}


@router.put("/registry/{dl_id}/reactivate", response_model=DlRegistryOut)
def reactivate_registry(
    dl_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DlRegistryOut:
    """Riattiva un distributore locale precedentemente disattivato."""
    _require_module(current_user)

    dl = db.query(DlRegistry).filter(DlRegistry.id == dl_id).first()
    if not dl:
        raise HTTPException(status_code=404, detail="Distributore non trovato")

    if dl.is_active:
        raise HTTPException(status_code=400, detail="Distributore già attivo")

    dl.is_active = True
    dl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dl)

    log_audit(
        db,
        "dl_registry_reactivated",
        user_id=current_user.id,
        detail={"dl_id": dl.id, "company_name": dl.company_name, "vat_number": dl.vat_number},
    )

    logger.info("DL riattivato: id=%d da %s", dl.id, current_user.username)
    return dl


@router.post("/registry/bulk", response_model=DlRegistryBulkResponse)
def bulk_create_registry(
    rows: list[DlRegistryBulkRow],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DlRegistryBulkResponse:
    """Caricamento massivo distributori locali da incolla Excel."""
    _require_module(current_user)

    if not rows:
        raise HTTPException(status_code=400, detail="Nessuna riga da elaborare")

    created = 0
    skipped = 0
    errors: list[DlRegistryBulkResultRow] = []

    existing_vats: set[str] = {
        r[0] for r in db.query(DlRegistry.vat_number).all()
    }
    batch_vats: set[str] = set()

    for row in rows:
        company = row.company_name.strip()
        vat = row.vat_number.strip()
        pec = row.pec_address.strip()

        if not company:
            errors.append(DlRegistryBulkResultRow(
                company_name=company, vat_number=vat, pec_address=pec,
                valid=False, error="Ragione sociale mancante",
            ))
            skipped += 1
            continue

        if not validate_partita_iva(vat):
            errors.append(DlRegistryBulkResultRow(
                company_name=company, vat_number=vat, pec_address=pec,
                valid=False, error="P.IVA non valida (deve essere 11 cifre con checksum corretto)",
            ))
            skipped += 1
            continue

        if not _EMAIL_RE.match(pec):
            errors.append(DlRegistryBulkResultRow(
                company_name=company, vat_number=vat, pec_address=pec,
                valid=False, error="Formato PEC non valido",
            ))
            skipped += 1
            continue

        if vat in batch_vats:
            errors.append(DlRegistryBulkResultRow(
                company_name=company, vat_number=vat, pec_address=pec,
                valid=False, error="P.IVA duplicata nel file",
            ))
            skipped += 1
            continue

        if vat in existing_vats:
            errors.append(DlRegistryBulkResultRow(
                company_name=company, vat_number=vat, pec_address=pec,
                valid=False, error="P.IVA già presente in anagrafica",
            ))
            skipped += 1
            continue

        dl = DlRegistry(
            company_name=company,
            vat_number=vat,
            pec_address=pec,
            is_active=True,
        )
        db.add(dl)
        batch_vats.add(vat)
        existing_vats.add(vat)
        created += 1

    db.commit()

    log_audit(
        db,
        "dl_registry_bulk_created",
        user_id=current_user.id,
        detail={
            "created": created,
            "skipped": skipped,
            "errors_count": len(errors),
        },
    )

    logger.info(
        "Caricamento massivo DL: creati=%d, saltati=%d — utente %s",
        created,
        skipped,
        current_user.username,
    )
    return DlRegistryBulkResponse(created=created, skipped=skipped, errors=errors)
