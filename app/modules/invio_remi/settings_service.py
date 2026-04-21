"""Persistenza impostazioni invio REMI su file JSON."""

import json
import logging
from pathlib import Path

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

_SETTINGS_PATH = BASE_DIR / "data" / "remi_settings.json"
_TEMPLATE_PATH = BASE_DIR / "data" / "remi_template.docx"

_DEFAULT_SETTINGS: dict = {
    "pec_account_id": None,
    "subject": "",
    "body_template": "",
    "docx_template_filename": "",
}


def load_settings() -> dict:
    """Legge le impostazioni dal file JSON. Restituisce i default se non esiste."""
    if not _SETTINGS_PATH.exists():
        return dict(_DEFAULT_SETTINGS)
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        # Assicura che tutte le chiavi di default siano presenti
        for key, default_val in _DEFAULT_SETTINGS.items():
            data.setdefault(key, default_val)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Errore lettura remi_settings.json, uso default: %s", exc)
        return dict(_DEFAULT_SETTINGS)


def save_settings(data: dict) -> None:
    """Salva le impostazioni nel file JSON."""
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_template_path() -> Path:
    """Restituisce il path del file DOCX template."""
    return _TEMPLATE_PATH


def template_exists() -> bool:
    """Verifica se il file DOCX template esiste."""
    return _TEMPLATE_PATH.exists()


def save_template(content: bytes) -> None:
    """Salva il file DOCX template (sovrascrittura diretta)."""
    _TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TEMPLATE_PATH.write_bytes(content)
