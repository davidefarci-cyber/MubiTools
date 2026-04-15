"""Pydantic models per il modulo Caricamento REMI — Anagrafica DL e Caricamento pratiche."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class DlRegistryCreate(BaseModel):
    """Richiesta creazione nuovo distributore locale."""

    company_name: str = Field(min_length=1, max_length=500)
    vat_number: str = Field(min_length=11, max_length=11)
    pec_address: str = Field(min_length=1, max_length=500)


class DlRegistryUpdate(BaseModel):
    """Richiesta modifica distributore locale."""

    company_name: str | None = Field(default=None, min_length=1, max_length=500)
    vat_number: str | None = Field(default=None, min_length=11, max_length=11)
    pec_address: str | None = Field(default=None, min_length=1, max_length=500)


class DlRegistryOut(BaseModel):
    """Risposta con dati distributore locale."""

    id: int
    company_name: str
    vat_number: str
    pec_address: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


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
