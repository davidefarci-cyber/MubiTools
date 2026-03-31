"""Pydantic models per il modulo Incassi Mubi."""

from pydantic import BaseModel


class UploadResponse(BaseModel):
    """Risposta all'upload di un file."""

    file_id: str
    filename: str
    size_bytes: int


class ProcessRequest(BaseModel):
    """Richiesta di avvio elaborazione."""

    file_incassi_id: str
    file_massivo_id: str
    file_conferimento_id: str
    file_piani_rientro_id: str | None = None


class ProcessResult(BaseModel):
    """Risultato dell'elaborazione incassi."""

    job_id: str
    status: str  # "pending" | "processing" | "completed" | "error"
    total_fatture: int = 0
    fatture_incassate: int = 0
    anomalie: int = 0
    piani_rientro: int = 0
    message: str = ""
