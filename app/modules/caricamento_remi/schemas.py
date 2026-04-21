"""Pydantic models per il modulo Caricamento REMI — Caricamento pratiche e dashboard."""

from datetime import date, datetime

from pydantic import BaseModel


# --- Caricamento pratiche REMI ---


class RemiMatchRow(BaseModel):
    """Singola riga di input per il match P.IVA."""

    vat_number: str
    remi_code: str


class RemiMatchResult(BaseModel):
    """Risultato match per una singola riga."""

    vat_number: str
    remi_code: str
    matched: bool
    company_name: str | None = None
    pec_address: str | None = None


class RemiConfirmRow(BaseModel):
    """Singola riga confermata per inserimento pratica."""

    vat_number: str
    remi_code: str
    company_name: str
    pec_address: str


class RemiConfirmRequest(BaseModel):
    """Richiesta conferma inserimento pratiche REMI."""

    effective_date: date
    rows: list[RemiConfirmRow]


class RemiConfirmResponse(BaseModel):
    """Risposta conferma inserimento pratiche REMI."""

    batch_id: str
    inserted: int
    skipped: int


# --- Dashboard ---


class RemiHistoryItem(BaseModel):
    """Singolo gruppo di pratiche aggregato per send_batch_id + DL."""

    send_batch_id: str | None
    vat_number: str
    company_name: str
    pec_address: str
    effective_date: date | None
    remi_codes: list[str]
    status: str
    sent_at: datetime | None = None
    error_detail: str | None = None
    practice_ids: list[int]


class RemiHistoryResponse(BaseModel):
    """Risposta paginata per lo storico pratiche."""

    total: int
    page: int
    items: list[RemiHistoryItem]


class RemiStatsResponse(BaseModel):
    """Statistiche riepilogative delle pratiche REMI."""

    total_practices: int
    pending: int
    sent: int
    errors: int
    cancelled: int
    last_send_date: datetime | None = None


class RemiResendRequest(BaseModel):
    """Richiesta reinvio pratiche in errore."""

    practice_ids: list[int]


class RemiResendResponse(BaseModel):
    """Risposta reinvio pratiche."""

    updated: int


class RemiChangeStatusRequest(BaseModel):
    """Richiesta cambio stato pratiche."""

    practice_ids: list[int]
    new_status: str


class RemiChangeStatusResponse(BaseModel):
    """Risposta cambio stato pratiche."""

    updated: int
