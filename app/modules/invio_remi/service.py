"""Orchestrazione business logic per il modulo Invio REMI.

Responsabilità:
- Anagrafica DL: CRUD, soft delete, riattivazione, caricamento massivo.
- Sincronizzazione pratiche pending con l'anagrafica.
- Aggregazione pratiche pending per distributore.
- Invio massivo PEC: genera PDF, invia PEC, aggiorna stato e yielda eventi SSE.

Gli errori di dominio vengono segnalati con ``HTTPException``: scelta pragmatica
per mantenere il router rigorosamente thin (un solo return per handler), in
deroga alla regola generale "niente FastAPI nei service". L'eventuale migrazione
a eccezioni di dominio custom è rimandata a un refactor trasversale.
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import DlRegistry, RemiPractice, log_audit
from app.modules.caricamento_remi.service import validate_partita_iva
from app.modules.invio_remi import email_service, settings_service
from app.shared.regex import is_valid_email
from app.modules.invio_remi.pdf_service import format_date_for_display, generate_pdf
from app.modules.invio_remi.schemas import (
    DlRegistryBulkResponse,
    DlRegistryBulkResultRow,
    DlRegistryBulkRow,
    DlRegistryCreate,
    DlRegistryUpdate,
)

logger = logging.getLogger(__name__)


# --- Settings / template upload ---------------------------------------------


async def save_settings_with_template(
    db: Session,
    user_id: int,
    *,
    pec_account_id: int | None,
    subject: str,
    body_template: str,
    docx_template_filename: str | None,
    docx_template_content: bytes | None,
) -> dict:
    """Aggiorna le impostazioni e, se fornito, persiste il template DOCX.

    ``docx_template_content`` è già stato letto dal router (``await UploadFile.read()``);
    qui si limita a validare estensione, salvare su disco e aggiornare il JSON.
    """
    settings_data = settings_service.load_settings()
    settings_data["pec_account_id"] = pec_account_id
    settings_data["subject"] = subject
    settings_data["body_template"] = body_template

    if docx_template_content is not None and docx_template_filename:
        if not docx_template_filename.lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="Il template deve essere un file .docx")
        settings_service.save_template(docx_template_content)
        settings_data["docx_template_filename"] = docx_template_filename
        logger.info("Template DOCX salvato: %s", docx_template_filename)

    settings_service.save_settings(settings_data)
    log_audit(db, "remi_settings_updated", user_id=user_id)

    return {"message": "Impostazioni salvate", "settings": settings_data}


# --- Sincronizzazione PEC da anagrafica -------------------------------------


def sync_pending_from_registry(db: Session, user_id: int) -> dict:
    """Aggiorna PEC e ragione sociale delle pratiche pending dall'anagrafica DL."""
    pending = (
        db.query(RemiPractice)
        .filter(RemiPractice.status == "pending")
        .all()
    )

    if not pending:
        return {"updated": 0, "message": "Nessuna pratica in attesa"}

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
            user_id=user_id,
            detail={"updated": updated_count, "total_pending": len(pending)},
        )

    return {"updated": updated_count, "total_pending": len(pending)}


# --- Pratiche pending aggregate per distributore ----------------------------


def list_pending_grouped(db: Session) -> list[dict]:
    """Restituisce le pratiche pending aggregate per distributore (vat_number)."""
    practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.status == "pending")
        .order_by(RemiPractice.vat_number, RemiPractice.id)
        .all()
    )

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


# --- Invio massivo PEC con streaming SSE ------------------------------------


def _prepare_send_all_payload(db: Session) -> tuple[dict, dict[str, dict]]:
    """Valida le impostazioni e serializza le pratiche pending per lo stream.

    Restituisce ``(settings_data, groups_data)`` dove ``groups_data`` è indicizzato
    per VAT con tutti i campi primitivi necessari al generatore (niente ORM:
    la sessione Depends viene chiusa prima che il generatore inizi a girare).
    """
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

    practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.status == "pending")
        .order_by(RemiPractice.vat_number, RemiPractice.id)
        .all()
    )

    if not practices:
        raise HTTPException(status_code=400, detail="Nessuna pratica in attesa di invio")

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

    return settings_data, groups_data


def _build_pec_body(
    body_template: str,
    *,
    company_name: str,
    pec_address: str,
    effective_date: str,
    remi_codes: list[str],
) -> str:
    """Sostituisce i tag del template testuale con i valori della pratica."""
    body = body_template
    body = body.replace("<REMI>", ", ".join(remi_codes))
    body = body.replace("<NOME_DL>", company_name)
    body = body.replace("<PEC_DL>", pec_address)
    body = body.replace("<DATA_DECORRENZA>", format_date_for_display(effective_date))
    body = body.replace("<DATA>", datetime.now().strftime("%d/%m/%Y"))
    return body


def _mark_practices_error(
    db: Session,
    practice_ids: list[int],
    *,
    error_detail: str,
    send_batch_id: str,
) -> None:
    dl_practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.id.in_(practice_ids))
        .all()
    )
    for p in dl_practices:
        p.status = "error"
        p.error_detail = error_detail
        p.send_batch_id = send_batch_id
    db.commit()


def _mark_practices_sent(
    db: Session,
    practice_ids: list[int],
    *,
    sent_at: datetime,
    send_batch_id: str,
) -> None:
    dl_practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.id.in_(practice_ids))
        .all()
    )
    for p in dl_practices:
        p.status = "sent"
        p.sent_at = sent_at
        p.send_batch_id = send_batch_id
    db.commit()


async def stream_send_all(db: Session, user_id: int) -> AsyncIterator[str]:
    """Avvia l'invio massivo e yielda eventi SSE (formato ``data: {json}\\n\\n``).

    - Valida settings e pratiche pending (può alzare ``HTTPException`` PRIMA
      del primo yield: il router gestisce la risposta di errore come oggi).
    - Per ogni DL: genera PDF, invia PEC, aggiorna stato, emette eventi
      ``generating_pdf`` / ``sending`` / ``sent`` / ``error`` e un finale
      ``complete``.
    """
    settings_data, groups_data = _prepare_send_all_payload(db)
    pec_account_id = settings_data["pec_account_id"]
    subject = settings_data.get("subject", "")
    body_template = settings_data.get("body_template", "")

    send_batch_id = str(uuid.uuid4())

    # Sessione indipendente: quella passata via Depends è già chiusa quando
    # il generator inizia a girare (StreamingResponse).
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
                _mark_practices_error(
                    gen_db, practice_ids,
                    error_detail=f"Errore generazione PDF: {error_msg}",
                    send_batch_id=send_batch_id,
                )
                error_count += 1
                yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'error', 'error': error_msg})}\n\n"
                continue

            yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'sending'})}\n\n"

            try:
                body = _build_pec_body(
                    body_template,
                    company_name=company_name,
                    pec_address=pec_address,
                    effective_date=effective_date,
                    remi_codes=remi_codes,
                )
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

                if result.get("success"):
                    _mark_practices_sent(
                        gen_db, practice_ids,
                        sent_at=datetime.now(timezone.utc),
                        send_batch_id=send_batch_id,
                    )
                    sent_count += 1
                    yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'sent'})}\n\n"
                else:
                    error_msg = result.get("error", "Errore sconosciuto")
                    _mark_practices_error(
                        gen_db, practice_ids,
                        error_detail=error_msg,
                        send_batch_id=send_batch_id,
                    )
                    error_count += 1
                    yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'error', 'error': error_msg})}\n\n"

            except Exception as exc:
                error_msg = str(exc)
                logger.exception("Errore invio PEC per DL %s", vat_number)
                _mark_practices_error(
                    gen_db, practice_ids,
                    error_detail=f"Errore invio: {error_msg}",
                    send_batch_id=send_batch_id,
                )
                error_count += 1
                yield f"data: {json.dumps({'vat_number': vat_number, 'status': 'error', 'error': error_msg})}\n\n"

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

        yield f"data: {json.dumps({'type': 'complete', 'sent': sent_count, 'errors': error_count})}\n\n"
    finally:
        gen_db.close()


# --- Anagrafica DL: CRUD + caricamento massivo ------------------------------


def list_registry(db: Session, search: str | None) -> list[DlRegistry]:
    """Lista distributori locali con filtro testo opzionale."""
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


def create_registry(db: Session, data: DlRegistryCreate, user_id: int, username: str) -> DlRegistry:
    """Crea un nuovo distributore locale (valida VAT, PEC, unicità)."""
    if not validate_partita_iva(data.vat_number):
        raise HTTPException(status_code=400, detail="Partita IVA non valida")

    if not is_valid_email(data.pec_address):
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
        user_id=user_id,
        detail={
            "dl_id": dl.id,
            "company_name": dl.company_name,
            "vat_number": dl.vat_number,
        },
    )

    logger.info("DL creato: %s (P.IVA %s) da %s", dl.company_name, dl.vat_number, username)
    return dl


def update_registry(
    db: Session,
    dl_id: int,
    data: DlRegistryUpdate,
    user_id: int,
    username: str,
) -> DlRegistry:
    """Modifica un distributore locale esistente (solo campi forniti)."""
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
        if not is_valid_email(data.pec_address):
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
        user_id=user_id,
        detail={"dl_id": dl.id, "company_name": dl.company_name, "vat_number": dl.vat_number},
    )

    logger.info("DL aggiornato: id=%d da %s", dl.id, username)
    return dl


def deactivate_registry(db: Session, dl_id: int, user_id: int, username: str) -> dict:
    """Disattiva un distributore locale (soft delete), bloccando se ha pratiche pending."""
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
        user_id=user_id,
        detail={"dl_id": dl.id, "company_name": dl.company_name, "vat_number": dl.vat_number},
    )

    logger.info("DL disattivato: id=%d da %s", dl.id, username)
    return {"detail": "Distributore disattivato"}


def reactivate_registry(db: Session, dl_id: int, user_id: int, username: str) -> DlRegistry:
    """Riattiva un distributore locale precedentemente disattivato."""
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
        user_id=user_id,
        detail={"dl_id": dl.id, "company_name": dl.company_name, "vat_number": dl.vat_number},
    )

    logger.info("DL riattivato: id=%d da %s", dl.id, username)
    return dl


def _bulk_validate_row(
    row: DlRegistryBulkRow,
    existing_vats: set[str],
    batch_vats: set[str],
) -> tuple[str, str, str, str | None]:
    """Normalizza e valida una riga. Ritorna ``(company, vat, pec, error_or_None)``."""
    company = row.company_name.strip()
    vat = row.vat_number.strip()
    pec = row.pec_address.strip()

    if not company:
        return company, vat, pec, "Ragione sociale mancante"
    if not validate_partita_iva(vat):
        return company, vat, pec, "P.IVA non valida (deve essere 11 cifre con checksum corretto)"
    if not is_valid_email(pec):
        return company, vat, pec, "Formato PEC non valido"
    if vat in batch_vats:
        return company, vat, pec, "P.IVA duplicata nel file"
    if vat in existing_vats:
        return company, vat, pec, "P.IVA già presente in anagrafica"
    return company, vat, pec, None


def bulk_create_registry(
    db: Session,
    rows: list[DlRegistryBulkRow],
    user_id: int,
    username: str,
) -> DlRegistryBulkResponse:
    """Caricamento massivo distributori locali da incolla Excel."""
    if not rows:
        raise HTTPException(status_code=400, detail="Nessuna riga da elaborare")

    created = 0
    skipped = 0
    errors: list[DlRegistryBulkResultRow] = []

    existing_vats: set[str] = {r[0] for r in db.query(DlRegistry.vat_number).all()}
    batch_vats: set[str] = set()

    for row in rows:
        company, vat, pec, error = _bulk_validate_row(row, existing_vats, batch_vats)
        if error:
            errors.append(DlRegistryBulkResultRow(
                company_name=company, vat_number=vat, pec_address=pec,
                valid=False, error=error,
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
        user_id=user_id,
        detail={
            "created": created,
            "skipped": skipped,
            "errors_count": len(errors),
        },
    )

    logger.info(
        "Caricamento massivo DL: creati=%d, saltati=%d — utente %s",
        created, skipped, username,
    )
    return DlRegistryBulkResponse(created=created, skipped=skipped, errors=errors)
