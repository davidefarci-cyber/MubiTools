"""Utility condivisa per il mapping di colonne Excel.

Centralizza i due pattern di ricerca colonne usati nei moduli:
- match esatto case-insensitive (usato da incassi_mubi)
- match substring case-insensitive (usato da connessione)
"""

from typing import Literal

import pandas as pd


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
    *,
    mode: Literal["exact", "substring"] = "exact",
) -> str | None:
    """Trova il nome colonna reale nel DataFrame tra i candidati.

    mode="exact": match esatto case-insensitive dopo strip (default).
    mode="substring": il candidato è contenuto nel nome colonna (case-insensitive).
    Restituisce il primo match o None.
    """
    if mode == "exact":
        lower_cols = {c.strip().lower(): c for c in df.columns}
        for candidate in candidates:
            if candidate.lower() in lower_cols:
                return lower_cols[candidate.lower()]
    elif mode == "substring":
        for candidate in candidates:
            for c in df.columns:
                if candidate.lower() in c.lower():
                    return c
    else:
        raise ValueError(f"mode non valido: {mode!r}")
    return None
