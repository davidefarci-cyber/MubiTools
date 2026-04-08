"""Logica di business per il modulo Connessione.

Sottofunzionalita': Crea Riga FILE A
Legge un file Excel (FILE B), mappa le colonne verso il formato FILE A,
applica trasformazioni sui valori e scrive il risultato come nuovo foglio.
"""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

logger = logging.getLogger(__name__)

# ===== Mappatura colonne FILE B -> FILE A =====
COL_MAPPING = {
    "ATTIVITA'": "ATTIVITA'",
    "DATA RICEZIONE": "OGGI",
    "DATA EVASIONE": "",
    "DATA INVIO 150": "",
    "NOTE": "",
    "COD SII": "",
    "VENDITORE": "",
    "RAGSOC": "RAGSOC",
    "CF": "CF",
    "P. IVA": "PIVA",
    "NR_TELEFONO": "NR_TELEFONO",
    "DUG FORNITURA": "DUG FORNITURA",
    "TOPONIMO": "INDIRIZZO FORNITURA",
    "CIVICO": "CIVICO FORNITURA",
    "CAP": "CAP FORNITURA",
    "COMUNE": "LOCALITA FORNITURA",
    "PROV": "PROVINCIA FORNITURA",
    "PDR": "PDR",
    "MATRICOLA": "MATRICOLA",
    "CODICE DL": "",
    "REMI": "REMI",
    "DL": "DISTRIBUTORE",
    "POTENZA": "Potenzialità massima richiesta (in kw)",
    "USO": "Tipo uso",
    "CATEGORIA D'USO": "categoria uso",
    "GG ": "gg utilizzo- classe di prelievo",
    "VOLUME ANNUO": "CONSUMO ANNUO TOTALE STIMATO",
    "DATA APP": "",
    "ORARIO APP": "",
    "COD. APP": "",
    "PREVENTIVO": "",
    "IMPONIBILE": "",
    "ACCETTAZIONE PREV": "",
    "STATO": "RICEZIONE ATTIVITA'",
    "NOTE 2": "",
}

# ===== Mappe valori =====
ATTIVITA_MAP = {
    "A01": "A01 - ATTIVAZIONE SEMPLICE",
    "A40": "A40 - ATTIVAZIONE CON ACCERTAMENTO",
    "PM1": "PM1 - PREVENTIVO MODIFICA IMPIANTO",
    "PN1": "PN1 - PREVENTIVO NUOVO IMPIANTO",
    "E01": "E01 - ESECUZIONE LAVORI",
    "D01": "D01 - DISATTIVAZIONE",
    "PR1": "PR1 - RIMOZIONE",
    "V01": "V01 - VERIFICA GDM",
    "V02": "V02 - VERIFICA PRESSIONE",
    "SM1": "SM1 - SOSPENSIONE MOROSITA'",
    "R01": "R01 - RIATTIVAZIONE MOROSITA'",
    "A02": "A02 - RIATTIVAZIONE P. INTERVENTO",
    "R40": "R40 - RIATTIVAZIONE CON ACCERTAMENTO",
    "V": "V - VOLTURA",
    "MU": "MU - MODIFICA USO",
    "SM2": "SM2 - TAGLIO COLONNA",
    "M02": "M02 - RICHIESTA DATI",
    "M01": "M01 - RETTIFICHE",
    "SPR": "SPR - CAMBIO CONTATORE",
}

CATEGORIA_USO_MAP = {
    "C1": "C1 - RISCALDAMENTO",
    "C2": "C2 - USO COTTURA CIBI E/O PRODUZIONE DI ACQUA CALDA SANITARIA",
    "C3": "C3 - RISCALDAMENTO/USO COTTURA CIBI E/O PRODUZIONE DI ACQUA CALDA SANITARIA",
    "C5": "C5 - USO CONDIZIONAMENTO E RISCALDAMENTO",
    "T1": "T1-1 - USO TECNOLOGICO (ARTIGIANALE-INDUSTRIALE) - 7 GIORNI",
    "T2": "T2-1 - USO TECNOLOGICO/RISCALDAMENTO - 7 GIORNI",
}

GG_MAP = {
    "A": "1 (= 7 gg)",
    "B": "2 (= 6 gg)",
    "C": "3 (= 5 gg)",
}

TIPO_USO_MAP = {
    "domestico": "DOMESTICO",
    "condominio domestico": "CONDOMINIO DOMESTICO",
    "usi diversi": "ALTRI USI",
    "pubblico": "USO PUBBLICO",
}

# Colonne indirizzo: col_a -> nome da cercare in FILE B
_INDIRIZZO_MAP = {
    "TOPONIMO": "INDIRIZZO FORNITURA",
    "CIVICO": "CIVICO FORNITURA",
    "CAP": "CAP FORNITURA",
    "COMUNE": "LOCALITA FORNITURA",
    "PROV": "PROVINCIA FORNITURA",
}


def _clean_val(val: object) -> str:
    """Pulisce un valore: rimuove .0 dai numeri e restituisce stringa vuota per valori nulli."""
    val = str(val).strip()
    if val in ("", "nan", "NaN", "None"):
        return ""
    if val.endswith(".0"):
        try:
            int(val[:-2])
            val = val[:-2]
        except ValueError:
            pass
    return val


def _find_col(df: pd.DataFrame, search_name: str) -> str | None:
    """Cerca una colonna nel dataframe con match case-insensitive parziale."""
    for c in df.columns:
        if search_name.lower() in c.lower():
            return c
    return None


def _build_row(df_b: pd.DataFrame, row_idx: int, warnings: set[str]) -> dict:
    """Costruisce una riga FILE A dalla riga row_idx del FILE B."""
    new_row: dict[str, object] = {}

    for col_a, source in COL_MAPPING.items():
        if source == "OGGI":
            new_row[col_a] = datetime.now().strftime("%d/%m/%Y")
        elif source == "RICEZIONE ATTIVITA'":
            new_row[col_a] = "RICEZIONE ATTIVITA'"
        elif source == "":
            new_row[col_a] = ""
        else:
            # Indirizzi
            if col_a in _INDIRIZZO_MAP:
                found_col = _find_col(df_b, _INDIRIZZO_MAP[col_a])
                if found_col:
                    val = _clean_val(df_b[found_col].iloc[row_idx])
                    val = val.upper() if val else ""
                else:
                    val = ""
                    warnings.add(f"Colonna '{_INDIRIZZO_MAP[col_a]}' non trovata per '{col_a}'")
                new_row[col_a] = val

            # PDR
            elif col_a == "PDR":
                if source in df_b.columns:
                    val = _clean_val(df_b[source].iloc[row_idx])
                else:
                    val = ""
                    warnings.add(f"Colonna '{source}' non trovata")
                new_row["PDR"] = val.upper() if val else ""
                new_row["LUNG."] = len(val) if val else ""

            # P. IVA e CF
            elif col_a in ("P. IVA", "CF"):
                if source in df_b.columns:
                    val = _clean_val(df_b[source].iloc[row_idx])
                else:
                    val = ""
                    warnings.add(f"Colonna '{source}' non trovata per '{col_a}'")
                new_row[col_a] = val.upper() if val else ""

            # Altri campi
            else:
                found_col = source if source in df_b.columns else _find_col(df_b, source)
                if found_col:
                    val = _clean_val(df_b[found_col].iloc[row_idx])
                    if val:
                        val = val.strip().upper()
                        if col_a == "ATTIVITA'" and val in ATTIVITA_MAP:
                            val = ATTIVITA_MAP[val].upper()
                        elif col_a == "CATEGORIA D'USO" and val in CATEGORIA_USO_MAP:
                            val = CATEGORIA_USO_MAP[val].upper()
                        elif col_a.strip() == "GG" and val in GG_MAP:
                            val = GG_MAP[val]
                        elif col_a == "USO" and val in TIPO_USO_MAP:
                            val = TIPO_USO_MAP[val].upper()
                    new_row[col_a] = val
                else:
                    new_row[col_a] = ""
                    warnings.add(f"Colonna sorgente '{source}' non trovata per '{col_a}'")

    return new_row


def crea_riga_file_a(file_path: Path, sheet_name: str = "Riga FILE A") -> dict:
    """Orchestratore: legge FILE B, mappa colonne, scrive foglio FILE A.

    Args:
        file_path: Path al file Excel (FILE B).
        sheet_name: Nome del foglio da creare nel file.

    Returns:
        dict con rows_created, warnings, output_path.
    """
    logger.info("Crea Riga FILE A: lettura %s", file_path.name)

    df_b = pd.read_excel(
        file_path,
        dtype={"PDR": str, "PIVA": str, "CF": str},
        keep_default_na=False,
        na_values=[],
    )
    df_b.columns = df_b.columns.str.strip()

    # Prendi solo le righe fino alla prima riga vuota
    valid_rows: list[int] = []
    for idx in range(len(df_b)):
        row = df_b.iloc[idx]
        has_data = any(
            str(v).strip() not in ("", "nan", "NaN", "None")
            for v in row
            if pd.notna(v)
        )
        if not has_data:
            break
        valid_rows.append(idx)

    if not valid_rows:
        raise ValueError("Il FILE B non contiene righe di dati")

    df_b = df_b.iloc[valid_rows].reset_index(drop=True)

    warnings: set[str] = set()
    rows: list[dict] = []
    for i in range(len(df_b)):
        rows.append(_build_row(df_b, i, warnings))

    df_new = pd.DataFrame(rows)

    # Scrivi nuovo foglio nel file originale
    book = load_workbook(file_path)
    if sheet_name in book.sheetnames:
        std = book[sheet_name]
        book.remove(std)
    book.save(file_path)
    book.close()

    with pd.ExcelWriter(file_path, engine="openpyxl", mode="a") as writer:
        df_new.to_excel(writer, sheet_name=sheet_name, index=False)

    logger.info("Crea Riga FILE A: %d righe create in '%s'", len(rows), sheet_name)

    return {
        "rows_created": len(rows),
        "warnings": sorted(warnings),
        "output_path": str(file_path),
    }
