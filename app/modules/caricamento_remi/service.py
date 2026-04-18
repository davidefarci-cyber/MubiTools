"""Servizi per il modulo Caricamento REMI."""

import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app.models import DlRegistry, RemiPractice
from app.modules.caricamento_remi.schemas import (
    RemiConfirmRequest,
    RemiHistoryItem,
    RemiMatchResult,
    RemiMatchRow,
    RemiStatsResponse,
)


# Transizioni di stato ammesse: {stato_corrente: {stati_destinazione}}
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"cancelled"},
    "cancelled": {"pending"},
    "sent": {"pending"},
}


def validate_partita_iva(piva: str) -> bool:
    """Valida una Partita IVA italiana con algoritmo di checksum.

    Regole:
    - Esattamente 11 cifre numeriche
    - L'ultima cifra è il carattere di controllo calcolato con l'algoritmo standard

    Returns:
        True se la P.IVA è valida, False altrimenti.
    """
    if not piva or len(piva) != 11 or not piva.isdigit():
        return False

    digits = [int(c) for c in piva]

    # Somma cifre in posizione dispari (indice 0, 2, 4, 6, 8) — 1-indexed: 1, 3, 5, 7, 9
    odd_sum = sum(digits[i] for i in range(0, 10, 2))

    # Somma cifre in posizione pari (indice 1, 3, 5, 7, 9) — 1-indexed: 2, 4, 6, 8, 10
    even_sum = 0
    for i in range(1, 10, 2):
        doubled = digits[i] * 2
        even_sum += (doubled // 10) + (doubled % 10)

    total = odd_sum + even_sum
    check_digit = (10 - (total % 10)) % 10

    return check_digit == digits[10]


def match_vat_numbers(
    rows: list[RemiMatchRow],
    db: Session,
) -> list[RemiMatchResult]:
    """Cerca ciascuna P.IVA nell'anagrafica distributori attivi.

    Per ogni riga restituisce un `RemiMatchResult` con `matched=True` e dati
    DL (company_name, pec_address) se la P.IVA è presente e attiva, altrimenti
    `matched=False` con campi nulli.
    """
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
    return results


def create_practices_batch(
    data: RemiConfirmRequest,
    db: Session,
) -> tuple[str, int, int]:
    """Inserisce un batch di pratiche REMI, saltando quelle senza company_name.

    Esegue `db.commit()`. Restituisce `(batch_id, inserted, skipped)`.
    """
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
    return batch_id, inserted, skipped


def list_practice_history(
    db: Session,
    status: str | None = None,
    vat_number: str | None = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[RemiHistoryItem], int]:
    """Storico pratiche aggregato per (vat_number, effective_date, batch_id).

    Stato del gruppo: peggiore fra quelli presenti nel gruppo, con priorità
    `error > pending > cancelled > sent`.

    Returns:
        (items paginati, total dei gruppi prima della paginazione).
    """
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

    groups: dict[tuple, list] = defaultdict(list)
    for p in practices:
        key = (p.vat_number, str(p.effective_date), p.batch_id)
        groups[key].append(p)

    items: list[RemiHistoryItem] = []
    for (_vat, _date, _batch), group in groups.items():
        first = group[0]
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
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total


def get_practices_stats(db: Session) -> RemiStatsResponse:
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


def reset_practices_to_pending(
    practice_ids: list[int],
    db: Session,
) -> list[int]:
    """Reimposta a `pending` le pratiche in `error` fra gli id indicati.

    Azzera `error_detail`, `send_batch_id`, `sent_at`. Esegue `db.commit()`.
    Restituisce la lista degli id effettivamente aggiornati (per audit).
    """
    practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.id.in_(practice_ids), RemiPractice.status == "error")
        .all()
    )

    for p in practices:
        p.status = "pending"
        p.error_detail = None
        p.send_batch_id = None
        p.sent_at = None

    db.commit()
    return [p.id for p in practices]


def transition_practices_status(
    practice_ids: list[int],
    new_status: str,
    db: Session,
) -> list[int]:
    """Applica una transizione di stato, validata da `_ALLOWED_TRANSITIONS`.

    Se `new_status` non è uno stato destinazione ammesso, solleva `ValueError`
    (il router lo mappa in `HTTPException(400)`). Le pratiche la cui
    transizione corrente→nuovo non è ammessa vengono saltate silenziosamente.

    Esegue `db.commit()`. Restituisce la lista degli id aggiornati.
    """
    if new_status not in {"pending", "cancelled"}:
        raise ValueError(f"Stato destinazione non valido: {new_status}")

    practices = (
        db.query(RemiPractice)
        .filter(RemiPractice.id.in_(practice_ids))
        .all()
    )

    updated: list[RemiPractice] = []
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
    return [p.id for p in updated]
