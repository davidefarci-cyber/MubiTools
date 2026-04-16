"""Pydantic models per il modulo Invio REMI — Anagrafica DL."""

from datetime import datetime

from pydantic import BaseModel, Field


class DlRegistryCreate(BaseModel):
    """Richiesta creazione nuovo distributore locale."""

    company_name: str = Field(min_length=1, max_length=500)
    vat_number: str = Field(min_length=11, max_length=11)
    pec_address: str = Field(min_length=1, max_length=500)


class DlRegistryBulkRow(BaseModel):
    """Singola riga per il caricamento massivo distributori."""

    company_name: str
    vat_number: str
    pec_address: str


class DlRegistryBulkResultRow(BaseModel):
    """Risultato validazione singola riga del caricamento massivo."""

    company_name: str
    vat_number: str
    pec_address: str
    valid: bool
    error: str | None = None


class DlRegistryBulkResponse(BaseModel):
    """Risposta inserimento massivo distributori."""

    created: int
    skipped: int
    errors: list[DlRegistryBulkResultRow]


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
