"""Validazioni e normalizzazioni valori per il modulo Incassi Mubi.

Raccoglie:
- `_normalize_amount`, `_normalize_date` — conversione valori atipici
  (stringhe con €, virgole, separatori di migliaia, date in formato europeo)
  in tipi Python/pandas canonici.
- `_validate_all_columns` — data-quality check sulla presenza delle colonne
  richieste a partire dai `debug_info` prodotti da
  `excel_reader._read_excel_smart`.
"""

import pandas as pd


def _normalize_amount(val: object) -> float:
    """Converte un valore in float, gestendo virgole e stringhe."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(".", "").replace(",", ".").replace("€", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _normalize_date(val: object) -> pd.Timestamp | None:
    """Converte un valore in datetime pandas."""
    if pd.isna(val):
        return None
    try:
        return pd.to_datetime(val, dayfirst=True)
    except (ValueError, TypeError):
        return None


def _validate_all_columns(debug_infos: list[dict]) -> list[dict]:
    """Valida che tutte le colonne richieste siano state trovate.

    Restituisce lista di errori (vuota = tutto ok).
    """
    errors = []
    for info in debug_infos:
        for col_label, variants in info.get("columns_missing", {}).items():
            errors.append({
                "file": info["file"],
                "sheet": info["sheet_used"],
                "sheets_available": info["sheets_available"],
                "colonna_attesa": col_label,
                "varianti_cercate": variants,
                "colonne_trovate": info["columns"],
            })
    return errors
