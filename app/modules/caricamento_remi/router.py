"""Router API per il modulo Caricamento REMI — caricamento pratiche e dashboard."""

import logging
import uuid
from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_module
from app.database import get_db
from app.models import DlRegistry, RemiPractice, User, log_audit
from app.modules.caricamento_remi.schemas import (
    RemiChangeStatusRequest,
    RemiChangeStatusResponse,
    RemiConfirmRequest,
    RemiConfirmResponse,
    RemiHistoryItem,
    RemiHistoryResponse,
    RemiMatchResult,
    RemiMatchRow,
    RemiResendRequest,
    RemiResendResponse,
    RemiStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MODULE_NAME = "caricamento_remi"


# --- Caricamento pratiche REMI ---


@router.post("/match", response_model=list[RemiMatchResult])
def match_practices(
    rows: list[RemiMatchRow],
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> list[RemiMatchResult]:
    """Esegue il match delle P.IVA contro l'anagrafica distributori attivi."""

    results: list[RemiMatchResult] = []
    for row in rows:
        vat = row.vat_number.strip()
        dl = (
            db.query(DlRegistry)
            .filter(DlRegistry.vat_number == vat, DlRegistry.is_active.is_(True))
            .first()
        )
        if dl:
            results.append(
                RemiMatchResult(
                    vat_number=vat,
                    remi_code=row.remi_code.strip(),
                    matched=True,
                    company_name=dl.company_name,
                    pec_address=dl.pec_address,
                )
            )
        else:
            results.append(
                RemiMatchResult(
                    vat_number=vat,
                    remi_code=row.remi_code.strip(),
                    matched=False,
                    company_name=None,
                    pec_address=None,
                )
            )

    logger.info(
        "Match pratiche: %d righe, %d trovate — utente %s",
        len(rows),
        sum(1 for r in results if r.matched),
        current_user.username,
    )
    return results


@router.post("/confirm", response_model=RemiConfirmResponse)
def confirm_practices(
    data: RemiConfirmRequest,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiConfirmResponse:
    """Conferma e inserisce le pratiche REMI nel database."""

    batch_id = str(uuid.uuid4())
    inserted = 0
    skipped = 0

    for row in data.rows:
        # Ignora righe senza company_name (non matched)
        if not row.company_name:
            skipped += 1
            continue

        practice = RemiPractice(
            vat_number=row.vat_number.strip(),
            company_name=row.company_name.strip(),
            pec_address=row.pec_address.strip(),
            remi_code=row.remi_code.strip(),
            effective_date=data.effective_date,
            status="pending",
            batch_id=batch_id,
        )
        db.add(practice)
        inserted += 1

    db.commit()

    log_audit(
        db,
        "remi_practices_loaded",
        user_id=current_user.id,
        detail={
            "batch_id": batch_id,
            "inserted": inserted,
            "skipped": skipped,
            "effective_date": str(data.effective_date),
        },
    )

    logger.info(
        "Pratiche REMI caricate: batch=%s, inserite=%d, saltate=%d — utente %s",
        batch_id,
        inserted,
        skipped,
        current_user.username,
    )
    return RemiConfirmResponse(batch_id=batch_id, inserted=inserted, skipped=skipped)


# --- Dashboard ---


@router.get("/history", response_model=RemiHistoryResponse)
def get_history(
    status: str | None = None,
    vat_number: str | None = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiHistoryResponse:
    """Storico pratiche REMI aggregato per DL + batch di invio, con filtri e paginazione."""

    query = db.query(RemiPractice)

    if status:
        query = query.filter(RemiPractice.status == status)
    if vat_number:
        query = query.filter(RemiPractice.vat_number == vat_number.strip())
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            RemiPractice.company_name.ilike(pattern) | RemiPractice.vat_number.ilike(pattern)
        )
    if date_from:
        query = query.filter(RemiPractice.effective_date >= date_from)
    if date_to:
        query = query.filter(RemiPractice.effective_date <= date_to)

    practices = query.order_by(RemiPractice.created_at.desc()).all()

    # Aggrega per (vat_number, effective_date, batch_id) per raggruppare le pratiche
    groups: dict[tuple, list] = defaultdict(list)
    for p in practices:
        key = (p.vat_number, str(p.effective_date), p.batch_id)
        groups[key].append(p)

    items: list[RemiHistoryItem] = []
    for (_vat, _date, _batch), group in groups.items():
        first = group[0]
        # Lo stato del gruppo è il peggiore: error > pending > cancelled > sent
        statuses = {p.status for p in group}
        if "error" in statuses:
            group_status = "error"
        elif "pending" in statuses:
            group_status = "pending"
        elif "cancelled" in statuses:
            group_status = "cancelled"
        else:
            group_status = "sent"

        error_details = [p.error_detail for p in group if p.error_detail]
        sent_dates = [p.sent_at for p in group if p.sent_at]

        items.append(
            RemiHistoryItem(
                send_batch_id=first.send_batch_id,
                vat_number=first.vat_number,
                company_name=first.company_name,
                pec_address=first.pec_address,
                effective_date=first.effective_date,
                remi_codes=[p.remi_code for p in group],
                status=group_status,
                sent_at=max(sent_dates) if sent_dates else None,
                error_detail="; ".join(error_details) if error_details else None,
                practice_ids=[p.id for p in group],
            )
        )

    total = len(items)

    # Paginazione
    start = (page - 1) * page_size
    end = start + page_size
    paginated = items[start:end]

    return RemiHistoryResponse(total=total, page=page, items=paginated)


@router.get("/history/stats", response_model=RemiStatsResponse)
def get_stats(
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiStatsResponse:
    """Statistiche riepilogative delle pratiche REMI."""

    total = db.query(RemiPractice).count()
    pending = db.query(RemiPractice).filter(RemiPractice.status == "pending").count()
    sent = db.query(RemiPractice).filter(RemiPractice.status == "sent").count()
    errors = db.query(RemiPractice).filter(RemiPractice.status == "error").count()
    cancelled = db.query(RemiPractice).filter(RemiPractice.status == "cancelled").count()

    last_sent = (
        db.query(RemiPractice.sent_at)
        .filter(RemiPractice.sent_at.isnot(None))
        .order_by(RemiPractice.sent_at.desc())
        .first()
    )
    last_send_date = last_sent[0] if last_sent else None

    return RemiStatsResponse(
        total_practices=total,
        pending=pending,
        sent=sent,
        errors=errors,
        cancelled=cancelled,
        last_send_date=last_send_date,
    )


@router.post("/history/resend", response_model=RemiResendResponse)
def resend_practices(
    data: RemiResendRequest,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiResendResponse:
    """Reimposta le pratiche in errore a stato pending per il reinvio."""

    practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.id.in_(data.practice_ids), RemiPractice.status == "error")
        .all()
    )

    for p in practices:
        p.status = "pending"
        p.error_detail = None
        p.send_batch_id = None
        p.sent_at = None

    db.commit()

    log_audit(
        db,
        "remi_practices_resend",
        user_id=current_user.id,
        detail={
            "practice_ids": [p.id for p in practices],
            "count": len(practices),
        },
    )

    logger.info(
        "Pratiche REMI reimpostate: %d pratiche — utente %s",
        len(practices),
        current_user.username,
    )
    return RemiResendResponse(updated=len(practices))


# Transizioni di stato ammesse: {stato_corrente: {stati_destinazione}}
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"cancelled"},
    "cancelled": {"pending"},
    "sent": {"pending"},
}


@router.post("/history/change-status", response_model=RemiChangeStatusResponse)
def change_practice_status(
    data: RemiChangeStatusRequest,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiChangeStatusResponse:
    """Cambia lo stato di un gruppo di pratiche REMI (transizioni validate)."""

    new_status = data.new_status
    if new_status not in {"pending", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"Stato destinazione non valido: {new_status}")

    practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.id.in_(data.practice_ids))
        .all()
    )

    updated = []
    for p in practices:
        allowed = _ALLOWED_TRANSITIONS.get(p.status, set())
        if new_status not in allowed:
            continue
        p.status = new_status
        if new_status == "pending":
            p.error_detail = None
            p.send_batch_id = None
            p.sent_at = None
        updated.append(p)

    db.commit()

    log_audit(
        db,
        "remi_change_status",
        user_id=current_user.id,
        detail={
            "practice_ids": [p.id for p in updated],
            "new_status": new_status,
            "count": len(updated),
        },
    )

    logger.info(
        "Cambio stato REMI: %d pratiche → %s — utente %s",
        len(updated),
        new_status,
        current_user.username,
    )
    return RemiChangeStatusResponse(updated=len(updated))
