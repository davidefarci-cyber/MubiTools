"""Router API per il modulo Caricamento REMI — Anagrafica DL e caricamento pratiche."""

import logging
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import DlRegistry, RemiPractice, User, log_audit
from app.modules.caricamento_remi.schemas import (
    DlRegistryCreate,
    DlRegistryOut,
    DlRegistryUpdate,
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
from app.modules.caricamento_remi.service import validate_partita_iva

logger = logging.getLogger(__name__)

router = APIRouter()

MODULE_NAME = "caricamento_remi"

# Regex semplice per validazione formato email/PEC
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _require_module(user: User) -> None:
    """Verifica che l'utente abbia accesso al modulo."""
    if not user.has_module(MODULE_NAME):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")


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

    # Validazione P.IVA
    if not validate_partita_iva(data.vat_number):
        raise HTTPException(status_code=400, detail="Partita IVA non valida")

    # Validazione formato PEC
    if not _EMAIL_RE.match(data.pec_address):
        raise HTTPException(status_code=400, detail="Formato PEC non valido")

    # Unicità P.IVA
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
        # Unicità P.IVA (escluso il record corrente)
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
    """Disattiva un distributore locale (soft delete).

    Blocca se ci sono pratiche REMI pending associate alla P.IVA.
    """
    _require_module(current_user)

    dl = db.query(DlRegistry).filter(DlRegistry.id == dl_id).first()
    if not dl:
        raise HTTPException(status_code=404, detail="Distributore non trovato")

    if not dl.is_active:
        raise HTTPException(status_code=400, detail="Distributore già disattivato")

    # Controlla pratiche pending associate
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


# --- Caricamento pratiche REMI ---


@router.post("/match", response_model=list[RemiMatchResult])
def match_practices(
    rows: list[RemiMatchRow],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RemiMatchResult]:
    """Esegue il match delle P.IVA contro l'anagrafica distributori attivi."""
    _require_module(current_user)

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RemiConfirmResponse:
    """Conferma e inserisce le pratiche REMI nel database."""
    _require_module(current_user)

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RemiHistoryResponse:
    """Storico pratiche REMI aggregato per DL + batch di invio, con filtri e paginazione."""
    _require_module(current_user)

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
        # Lo stato del gruppo è il peggiore: error > pending > sent
        statuses = {p.status for p in group}
        if "error" in statuses:
            group_status = "error"
        elif "pending" in statuses:
            group_status = "pending"
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RemiStatsResponse:
    """Statistiche riepilogative delle pratiche REMI."""
    _require_module(current_user)

    total = db.query(RemiPractice).count()
    pending = db.query(RemiPractice).filter(RemiPractice.status == "pending").count()
    sent = db.query(RemiPractice).filter(RemiPractice.status == "sent").count()
    errors = db.query(RemiPractice).filter(RemiPractice.status == "error").count()

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
        last_send_date=last_send_date,
    )


@router.post("/history/resend", response_model=RemiResendResponse)
def resend_practices(
    data: RemiResendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RemiResendResponse:
    """Reimposta le pratiche in errore a stato pending per il reinvio."""
    _require_module(current_user)

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
