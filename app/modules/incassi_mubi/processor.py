"""Pipeline di elaborazione Incassi Mubi — le 6 fasi.

Ogni fase è una funzione pura che riceve uno o più DataFrame/Path e
restituisce DataFrame aggiornati + metadata. Sono chiamate in sequenza
da `service.elabora_incassi` nell'ordine definito:

1. `fase1_parse_incassi`         — parsing del file TXT esportato da Mubi
2. `fase2_join_importo_aperto`   — join massivo ↔ incassi su numero fattura
3. `fase3_piani_rientro`         — annotazione piani di rientro nel conferimento
4. `fase4_popola_conferimento`   — popola INCASSATO / DATA PAG / MODALITA'
5. `fase5_calcolo_incassato`     — calcola l'effettivo incassato come differenza
6. `fase6_ordinamento_controllo` — ordina e individua anomalie
"""

import logging
from pathlib import Path

import pandas as pd

from app.modules.incassi_mubi.excel_reader import (
    COL_DATA_PAGAMENTO_VARIANTS,
    COL_DATA_SCADENZA_VARIANTS,
    COL_IMPORTO_APERTO_VARIANTS,
    COL_MODALITA_PAGAMENTO_VARIANTS,
    COL_NR_BOLLETTA_VARIANTS,
    COL_NR_DOCUMENTO_VARIANTS,
    _find_column,
    _read_excel_smart,
)
from app.modules.incassi_mubi.validator import _normalize_amount, _normalize_date

logger = logging.getLogger(__name__)


# ─── FASE 1: Conversione file Incassi ─────────────────────────────

def fase1_parse_incassi(file_path: Path) -> pd.DataFrame:
    """Parsa il file TXT esportato da Mubi e lo converte in DataFrame.

    Rileva automaticamente il separatore (tab, punto e virgola, pipe, virgola).
    Normalizza date e importi.
    """
    logger.info("FASE 1: Parsing file incassi %s", file_path.name)

    # Rileva separatore
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        sample = f.read(4096)

    candidates = {"\t": sample.count("\t"), ";": sample.count(";"), "|": sample.count("|"), ",": sample.count(",")}
    sep = max(candidates, key=candidates.get) if any(candidates.values()) else ","

    logger.info("  Separatore rilevato: %r", sep)

    df = pd.read_csv(file_path, sep=sep, encoding="utf-8-sig", encoding_errors="replace", dtype=str)
    # Pulisce nomi colonna: strip spazi e rimuove eventuali BOM residui
    df.columns = [c.strip().replace("\ufeff", "") for c in df.columns]

    logger.info("  Colonne trovate nel file incassi: %s", list(df.columns))

    # Strip spazi da tutte le celle stringa
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace("nan", pd.NA)

    # Normalizza importi nelle colonne rilevanti
    for variants in [COL_IMPORTO_APERTO_VARIANTS]:
        col_name = _find_column(df, variants)
        if col_name:
            df[col_name] = df[col_name].apply(_normalize_amount)

    # Normalizza date
    for variants in [COL_DATA_PAGAMENTO_VARIANTS, COL_DATA_SCADENZA_VARIANTS]:
        col_name = _find_column(df, variants)
        if col_name:
            df[col_name] = df[col_name].apply(_normalize_date)

    logger.info("  File incassi: %d righe, %d colonne", len(df), len(df.columns))
    return df


# ─── FASE 2: Cerca.Vert Importo Aperto ───────────────────────────

def fase2_join_importo_aperto(
    df_incassi: pd.DataFrame,
    file_massivo: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """JOIN tra massivo e incassi su numero fattura.

    Per ogni riga del massivo, cerca l'importo aperto dal file incassi.
    Identifica fatture con importo aperto > 20 euro (nuove righe da
    aggiungere al conferimento).

    Returns:
        (df_massivo arricchito, df_nuove_righe, df_incassi originale)
    """
    logger.info("FASE 2: Join massivo con file incassi per ImportoAperto")

    df_massivo, debug_massivo = _read_excel_smart(
        file_massivo,
        required_variants=[COL_NR_BOLLETTA_VARIANTS],
        label="massivo",
    )

    # Trova colonne chiave
    col_boll_incassi = _find_column(df_incassi, COL_NR_BOLLETTA_VARIANTS)
    col_boll_massivo = _find_column(df_massivo, COL_NR_BOLLETTA_VARIANTS)
    col_importo_incassi = _find_column(df_incassi, COL_IMPORTO_APERTO_VARIANTS)

    if not col_boll_incassi:
        raise ValueError("Colonna 'numerofattura' non trovata nel file incassi")
    if not col_boll_massivo:
        raise ValueError("Colonna 'numerofattura' non trovata nel file massivo")
    if not col_importo_incassi:
        raise ValueError("Colonna 'importo aperto' non trovata nel file incassi")

    # Prepara chiavi di join
    df_massivo["_join_key"] = df_massivo[col_boll_massivo].astype(str).str.strip()
    df_incassi["_join_key"] = df_incassi[col_boll_incassi].astype(str).str.strip()

    # Prendi importo aperto dal file incassi (deduplica su numero fattura)
    # Rinomino in "ImportoAperto_Incassi" per evitare collisione con la colonna
    # "ImportoAperto" già presente nel massivo
    incassi_subset = df_incassi[["_join_key", col_importo_incassi]].copy()
    incassi_subset[col_importo_incassi] = incassi_subset[col_importo_incassi].apply(_normalize_amount)
    incassi_subset = incassi_subset.drop_duplicates(subset=["_join_key"], keep="first")
    incassi_subset = incassi_subset.rename(columns={col_importo_incassi: "ImportoAperto_Incassi"})

    # LEFT JOIN: massivo come base, lookup importo aperto dagli incassi
    df_massivo = df_massivo.merge(incassi_subset, on="_join_key", how="left")
    df_massivo["ImportoAperto_Incassi"] = df_massivo["ImportoAperto_Incassi"].fillna(0.0)

    # Aggiungi data di lavorazione (data odierna)
    df_massivo["Data Lavorazione"] = pd.Timestamp.now().normalize()

    # Nuove righe: importo aperto incassi > 20 euro (soglia conferimento)
    df_nuove = df_massivo[df_massivo["ImportoAperto_Incassi"] > 20].copy()

    logger.info("  Join completato: %d righe massivo, %d nuove righe da aggiungere (ImportoAperto > 20)",
                len(df_massivo), len(df_nuove))
    return df_massivo, df_nuove, df_incassi, debug_massivo


# ─── FASE 3: Piani di Rientro ────────────────────────────────────

def fase3_piani_rientro(
    df_conferimento: pd.DataFrame,
    file_piani: Path | None,
) -> tuple[pd.DataFrame, int, dict | None]:
    """JOIN tra piani di rientro e conferimento.

    Per ogni match: aggiunge 'PIANO DI RIENTRO' nella colonna NOTE.

    Returns:
        (df_conferimento aggiornato, conteggio_piani, debug_info_piani)
    """
    if file_piani is None:
        logger.info("FASE 3: Nessun file piani di rientro, skip")
        return df_conferimento, 0, None

    logger.info("FASE 3: Piani di rientro")

    df_piani, debug_piani = _read_excel_smart(
        file_piani,
        required_variants=[COL_NR_DOCUMENTO_VARIANTS],
        label="piani_rientro",
    )

    col_boll_conf = _find_column(df_conferimento, COL_NR_BOLLETTA_VARIANTS)
    col_boll_piani = _find_column(df_piani, COL_NR_DOCUMENTO_VARIANTS)

    if not col_boll_conf or not col_boll_piani:
        logger.warning("  Colonna numero fattura/documento non trovata, skip piani di rientro")
        return df_conferimento, 0, debug_piani

    piani_set = set(df_piani[col_boll_piani].astype(str).str.strip())

    # Trova o crea colonna NOTE
    col_note = None
    for c in df_conferimento.columns:
        if c.strip().upper() == "NOTE":
            col_note = c
            break
    if col_note is None:
        col_note = "NOTE"
        df_conferimento[col_note] = ""

    count = 0
    for idx, row in df_conferimento.iterrows():
        boll = str(row[col_boll_conf]).strip()
        if boll in piani_set:
            existing_note = str(row[col_note]) if pd.notna(row[col_note]) else ""
            if "PIANO DI RIENTRO" not in existing_note.upper():
                df_conferimento.at[idx, col_note] = (
                    (existing_note + " " if existing_note else "") + "PIANO DI RIENTRO"
                ).strip()
                count += 1

    logger.info("  Piani di rientro trovati: %d", count)
    return df_conferimento, count, debug_piani


# ─── FASE 4: Popola colonne Conferimento ─────────────────────────

def fase4_popola_conferimento(
    df_conferimento: pd.DataFrame,
    df_incassi: pd.DataFrame,
) -> pd.DataFrame:
    """Cerca.Vert tra incassi e conferimento su numero fattura.

    Popola:
    - Colonna INCASSATO: importo aperto dal file incassi
    - Colonna DATA PAGAMENTO: data pagamento dal file incassi
    - Colonna MODALITA' DI PAGAMENTO: metodo pagamento dal file incassi
    """
    logger.info("FASE 4: Popola colonne Conferimento (INCASSATO, DATA PAGAMENTO, MODALITA')")

    col_boll_conf = _find_column(df_conferimento, COL_NR_BOLLETTA_VARIANTS)
    col_boll_inc = _find_column(df_incassi, COL_NR_BOLLETTA_VARIANTS)

    if not col_boll_conf or not col_boll_inc:
        raise ValueError("Colonna numero fattura non trovata")

    # Prepara lookup da incassi
    col_importo = _find_column(df_incassi, COL_IMPORTO_APERTO_VARIANTS)
    col_data_pag = _find_column(df_incassi, COL_DATA_PAGAMENTO_VARIANTS)
    col_mod_pag = _find_column(df_incassi, COL_MODALITA_PAGAMENTO_VARIANTS)

    # Crea dizionario lookup dal file incassi
    lookup: dict[str, dict] = {}
    for _, row in df_incassi.iterrows():
        key = str(row[col_boll_inc]).strip()
        entry: dict = {}
        if col_importo and pd.notna(row.get(col_importo)):
            entry["importo"] = _normalize_amount(row[col_importo])
        if col_data_pag and pd.notna(row.get(col_data_pag)):
            entry["data_pag"] = row[col_data_pag]
        if col_mod_pag and pd.notna(row.get(col_mod_pag)):
            entry["mod_pag"] = str(row[col_mod_pag])
        if entry:
            lookup[key] = entry

    # Trova colonne target nel conferimento per nome
    col_z = _find_column(df_conferimento, ["incassato", "importo incassato"])
    col_aa = _find_column(df_conferimento, COL_DATA_PAGAMENTO_VARIANTS)
    col_ab = _find_column(df_conferimento, COL_MODALITA_PAGAMENTO_VARIANTS)

    # Se non trovate, crearle
    if not col_z:
        col_z = "INCASSATO"
        df_conferimento[col_z] = ""
    if not col_aa:
        col_aa = "DATA PAGAMENTO"
        df_conferimento[col_aa] = ""
    if not col_ab:
        col_ab = "MODALITA' DI PAGAMENTO"
        df_conferimento[col_ab] = ""

    populated = 0
    for idx, row in df_conferimento.iterrows():
        key = str(row[col_boll_conf]).strip()
        if key in lookup:
            data = lookup[key]
            if "importo" in data:
                df_conferimento.at[idx, col_z] = data["importo"]
            if "data_pag" in data:
                df_conferimento.at[idx, col_aa] = data["data_pag"]
            if "mod_pag" in data:
                df_conferimento.at[idx, col_ab] = data["mod_pag"]
            populated += 1

    logger.info("  Righe popolate nel conferimento: %d", populated)
    return df_conferimento


# ─── FASE 5: Calcolo Incassato ───────────────────────────────────

def fase5_calcolo_incassato(df_conferimento: pd.DataFrame) -> pd.DataFrame:
    """Calcola il valore effettivo di INCASSATO.

    INCASSATO = ImportoAperto(conferimento, col Q) - ImportoAperto(incassi, attualmente in col Z).
    Se uguali → 0 (nessun pagamento). Se diversi → differenza = importo incassato.
    """
    logger.info("FASE 5: Calcolo Incassato (ImportoAperto_conf - ImportoAperto_incassi)")

    # Colonna Q = "importo aperto" nel conferimento (importo aperto al tempo t-1)
    col_q = _find_column(df_conferimento, COL_IMPORTO_APERTO_VARIANTS)
    # Colonna Z = "INCASSATO" (attualmente contiene l'importo aperto dal file incassi)
    col_z = _find_column(df_conferimento, ["incassato", "importo incassato"])

    if not col_q or not col_z:
        logger.warning("  Colonne 'importo aperto' o 'INCASSATO' non trovate, skip fase 5")
        return df_conferimento

    calcolati = 0
    for idx, row in df_conferimento.iterrows():
        val_z = _normalize_amount(row.get(col_z, 0))
        val_q = _normalize_amount(row.get(col_q, 0))

        if val_z != 0:
            # Incassato effettivo = importo aperto precedente - importo aperto attuale
            df_conferimento.at[idx, col_z] = round(val_q - val_z, 2)
            calcolati += 1

    logger.info("  Incassato calcolato per %d righe", calcolati)
    return df_conferimento


# ─── FASE 6: Ordinamento e Controllo ─────────────────────────────

def fase6_ordinamento_controllo(
    df_conferimento: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict]]:
    """Ordina INCASSATO e genera report anomalie.

    Returns:
        (df_conferimento_ordinato, anomalie)
    """
    logger.info("FASE 6: Ordinamento e controllo")

    col_z = _find_column(df_conferimento, ["incassato", "importo incassato"])
    col_aa = _find_column(df_conferimento, COL_DATA_PAGAMENTO_VARIANTS)
    col_ab = _find_column(df_conferimento, COL_MODALITA_PAGAMENTO_VARIANTS)
    col_boll = _find_column(df_conferimento, COL_NR_BOLLETTA_VARIANTS)

    # Converti colonna INCASSATO in numerico per ordinamento
    if col_z:
        df_conferimento[col_z] = df_conferimento[col_z].apply(_normalize_amount)
        df_conferimento = df_conferimento.sort_values(by=col_z, ascending=True)

    anomalie: list[dict] = []

    for idx, row in df_conferimento.iterrows():
        val_z = _normalize_amount(row.get(col_z, 0)) if col_z else 0
        boll = str(row.get(col_boll, idx)) if col_boll else str(idx)

        if val_z != 0:
            # Verifica dati mancanti
            has_data = col_aa and pd.notna(row.get(col_aa)) and str(row.get(col_aa, "")).strip()
            has_mod = col_ab and pd.notna(row.get(col_ab)) and str(row.get(col_ab, "")).strip()

            if not has_data or not has_mod:
                missing = []
                if not has_data:
                    missing.append("DATA PAGAMENTO")
                if not has_mod:
                    missing.append("MODALITA' DI PAGAMENTO")
                anomalie.append({
                    "numero_bolletta": boll,
                    "tipo": "dati_mancanti",
                    "dettaglio": f"Mancante: {', '.join(missing)}",
                })

    logger.info("  Anomalie: %d", len(anomalie))
    return df_conferimento, anomalie
