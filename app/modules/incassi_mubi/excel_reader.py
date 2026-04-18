"""Lettura smart di file Excel e costanti di riconoscimento colonne.

Mantiene le `COL_*_VARIANTS` (varianti di nome colonna accettate
case-insensitive) e le utility per trovare colonne / caricare il foglio
giusto da file `.xlsx` con header variabile.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Nomi colonna normalizzati (case-insensitive matching)
COL_NR_BOLLETTA_VARIANTS = [
    "nr. bolletta", "numero bolletta", "nr bolletta",
    "n. bolletta", "num bolletta", "nr.bolletta",
    "numerofattura",
]
COL_NR_DOCUMENTO_VARIANTS = [
    "nr. documento", "numero documento", "nr documento", "n. documento",
]
COL_IMPORTO_APERTO_VARIANTS = [
    "importo aperto", "importoaperto", "imp. aperto", "imp aperto",
]
COL_DATA_PAGAMENTO_VARIANTS = [
    "data pagamento", "data pag.", "data pag", "datapagamento",
]
COL_MODALITA_PAGAMENTO_VARIANTS = [
    "modalita' di pagamento", "modalita di pagamento",
    "mod. pagamento", "mod pagamento", "modalitapagamento",
    "metodopagamento",
]
COL_DATA_SCADENZA_VARIANTS = [
    "data scadenza", "datascadenza", "data scad.", "scadenza",
]


def _find_column(df: pd.DataFrame, variants: list[str]) -> str | None:
    """Trova il nome colonna reale nel DataFrame tra le varianti."""
    lower_cols = {c.strip().lower(): c for c in df.columns}
    for variant in variants:
        if variant.lower() in lower_cols:
            return lower_cols[variant.lower()]
    return None


def _read_excel_smart(
    file_path: Path,
    required_variants: list[list[str]],
    label: str = "file",
) -> tuple[pd.DataFrame, dict]:
    """Carica un file Excel trovando automaticamente il foglio giusto.

    Prova il primo foglio; se mancano colonne attese, prova gli altri.
    Restituisce (DataFrame, debug_info).
    """
    xl = pd.ExcelFile(file_path)
    all_sheets = xl.sheet_names
    debug = {"file": label, "sheets_available": all_sheets, "sheet_used": None, "columns": [], "columns_matched": {}, "columns_missing": {}}

    best_df = None
    best_sheet = None
    best_found = -1

    for sheet in all_sheets:
        df = pd.read_excel(xl, sheet_name=sheet, dtype=str)
        df.columns = [c.strip().replace("\ufeff", "") for c in df.columns]

        found_count = 0
        for variants in required_variants:
            if _find_column(df, variants):
                found_count += 1

        if found_count > best_found:
            best_found = found_count
            best_df = df
            best_sheet = sheet

        # Se tutte le colonne trovate, usiamo questo foglio
        if found_count == len(required_variants):
            break

    xl.close()

    debug["sheet_used"] = best_sheet
    debug["columns"] = list(best_df.columns) if best_df is not None else []

    # Report colonne trovate/mancanti
    for variants in required_variants:
        col = _find_column(best_df, variants) if best_df is not None else None
        key = variants[0]
        if col:
            debug["columns_matched"][key] = col
        else:
            debug["columns_missing"][key] = variants

    logger.info("  [%s] Fogli: %s | Foglio usato: '%s' | Colonne: %s",
                label, all_sheets, best_sheet, debug["columns"])

    if debug["columns_missing"]:
        logger.warning("  [%s] COLONNE MANCANTI: %s", label, debug["columns_missing"])

    return best_df, debug
