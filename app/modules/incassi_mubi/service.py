"""Logica di business per il modulo Incassi Mubi.

Implementa le 6 fasi di elaborazione:
1. Conversione file Incassi (.txt -> DataFrame)
2. Cerca.Vert Importo Aperto (join Massivo con Incassi)
3. Piani di Rientro (join e annotazione)
4. Popola colonne Conferimento (INCASSATO, DATA PAGAMENTO, MODALITA')
5. Calcolo Incassato (ImportoAperto_conferimento - ImportoAperto_incassi)
6. Ordinamento e Controllo
"""

import logging
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

logger = logging.getLogger(__name__)

RED_FILL = PatternFill(start_color="FFE74C3C", end_color="FFE74C3C", fill_type="solid")

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

    df = pd.read_csv(file_path, sep=sep, encoding="utf-8", encoding_errors="replace", dtype=str)
    df.columns = [c.strip() for c in df.columns]

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
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """JOIN tra massivo e incassi su numero fattura.

    Per ogni riga del massivo, cerca l'importo aperto dal file incassi.
    Identifica fatture con importo aperto > 20 euro (nuove righe da
    aggiungere al conferimento).

    Returns:
        (df_massivo arricchito, df_nuove_righe, df_incassi originale)
    """
    logger.info("FASE 2: Join massivo con file incassi per ImportoAperto")

    df_massivo = pd.read_excel(file_massivo, dtype=str)
    df_massivo.columns = [c.strip() for c in df_massivo.columns]

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
    incassi_subset = df_incassi[["_join_key", col_importo_incassi]].copy()
    incassi_subset[col_importo_incassi] = incassi_subset[col_importo_incassi].apply(_normalize_amount)
    incassi_subset = incassi_subset.drop_duplicates(subset=["_join_key"], keep="first")
    incassi_subset = incassi_subset.rename(columns={col_importo_incassi: "ImportoAperto"})

    # LEFT JOIN: massivo come base, lookup importo aperto dagli incassi
    df_massivo = df_massivo.merge(incassi_subset, on="_join_key", how="left")
    df_massivo["ImportoAperto"] = df_massivo["ImportoAperto"].fillna(0.0)

    # Aggiungi data di lavorazione (data odierna)
    df_massivo["Data Lavorazione"] = pd.Timestamp.now().normalize()

    # Nuove righe: importo aperto > 20 euro (soglia conferimento)
    df_nuove = df_massivo[df_massivo["ImportoAperto"] > 20].copy()

    logger.info("  Join completato: %d righe massivo, %d nuove righe da aggiungere (ImportoAperto > 20)",
                len(df_massivo), len(df_nuove))
    return df_massivo, df_nuove, df_incassi


# ─── FASE 3: Piani di Rientro ────────────────────────────────────

def fase3_piani_rientro(
    df_conferimento: pd.DataFrame,
    file_piani: Path | None,
) -> tuple[pd.DataFrame, int]:
    """JOIN tra piani di rientro e conferimento.

    Per ogni match: aggiunge 'PIANO DI RIENTRO' nella colonna NOTE.

    Returns:
        (df_conferimento aggiornato, conteggio_piani)
    """
    if file_piani is None:
        logger.info("FASE 3: Nessun file piani di rientro, skip")
        return df_conferimento, 0

    logger.info("FASE 3: Piani di rientro")

    df_piani = pd.read_excel(file_piani, dtype=str)
    df_piani.columns = [c.strip() for c in df_piani.columns]

    col_boll_conf = _find_column(df_conferimento, COL_NR_BOLLETTA_VARIANTS)
    col_boll_piani = _find_column(df_piani, COL_NR_DOCUMENTO_VARIANTS)

    if not col_boll_conf or not col_boll_piani:
        logger.warning("  Colonna numero fattura/documento non trovata, skip piani di rientro")
        return df_conferimento, 0

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
    return df_conferimento, count


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


# ─── Salvataggio output ──────────────────────────────────────────

def salva_conferimento(
    df_conferimento: pd.DataFrame,
    anomalie: list[dict],
    output_path: Path,
    template_path: Path | None = None,
) -> None:
    """Salva il DataFrame conferimento aggiornato in un file Excel.

    Evidenzia in rosso le righe con anomalie.
    """
    logger.info("Salvataggio conferimento aggiornato: %s", output_path)

    col_boll = _find_column(df_conferimento, COL_NR_BOLLETTA_VARIANTS)
    anomaly_bollette = {a["numero_bolletta"] for a in anomalie}

    # Salva con openpyxl per poter applicare stili
    df_conferimento.to_excel(output_path, index=False, engine="openpyxl")

    wb = load_workbook(output_path)
    ws = wb.active

    if col_boll:
        boll_col_idx = list(df_conferimento.columns).index(col_boll) + 1
        for row_idx in range(2, ws.max_row + 1):
            cell_val = str(ws.cell(row=row_idx, column=boll_col_idx).value or "").strip()
            if cell_val in anomaly_bollette:
                for col_idx in range(1, ws.max_column + 1):
                    ws.cell(row=row_idx, column=col_idx).fill = RED_FILL

    wb.save(output_path)
    wb.close()
    logger.info("  File salvato: %d righe", len(df_conferimento))


def salva_report_anomalie(anomalie: list[dict], output_path: Path) -> None:
    """Salva il report anomalie in un file Excel."""
    if not anomalie:
        return
    df = pd.DataFrame(anomalie)
    df.to_excel(output_path, index=False, engine="openpyxl")
    logger.info("Report anomalie salvato: %d righe -> %s", len(df), output_path)


def salva_nuove_righe(df_nuove: pd.DataFrame, output_path: Path) -> None:
    """Salva le nuove righe da aggiungere al conferimento."""
    if df_nuove.empty:
        return
    df_nuove.to_excel(output_path, index=False, engine="openpyxl")
    logger.info("Nuove righe salvate: %d -> %s", len(df_nuove), output_path)


# ─── Orchestratore ────────────────────────────────────────────────

def elabora_incassi(
    file_incassi: Path,
    file_massivo: Path,
    file_conferimento: Path,
    file_piani: Path | None,
    output_dir: Path,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict:
    """Esegue le 6 fasi di elaborazione e restituisce i risultati.

    Args:
        file_incassi: Path al file .txt esportato da Mubi
        file_massivo: Path al file .xlsx estrazione massiva
        file_conferimento: Path al file .xlsx conferimento
        file_piani: Path al file .xlsx piani di rientro (opzionale)
        output_dir: Directory dove salvare i file output
        progress_callback: Funzione(phase, message) per aggiornare lo stato

    Returns:
        Dizionario con risultati e percorsi file output.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    def notify(phase: int, msg: str) -> None:
        logger.info("  [Fase %d] %s", phase, msg)
        if progress_callback:
            progress_callback(phase, msg)

    # FASE 1
    notify(1, "Parsing file incassi...")
    df_incassi = fase1_parse_incassi(file_incassi)
    notify(1, f"Completato: {len(df_incassi)} righe")

    # FASE 2
    notify(2, "Join massivo con incassi per ImportoAperto...")
    df_massivo, df_nuove_righe, df_incassi = fase2_join_importo_aperto(df_incassi, file_massivo)
    notify(2, f"Completato: {len(df_nuove_righe)} nuove righe (ImportoAperto > 20)")

    # Carica conferimento
    df_conferimento = pd.read_excel(file_conferimento, dtype=str)
    df_conferimento.columns = [c.strip() for c in df_conferimento.columns]

    # FASE 3
    notify(3, "Verifica piani di rientro...")
    df_conferimento, piani_count = fase3_piani_rientro(
        df_conferimento, file_piani
    )
    notify(3, f"Completato: {piani_count} piani trovati")

    # FASE 4
    notify(4, "Popola colonne Conferimento...")
    df_conferimento = fase4_popola_conferimento(df_conferimento, df_incassi)
    notify(4, "Completato")

    # FASE 5
    notify(5, "Calcolo Incassato...")
    df_conferimento = fase5_calcolo_incassato(df_conferimento)
    notify(5, "Completato")

    # FASE 6
    notify(6, "Ordinamento e controllo...")
    df_conferimento, anomalie = fase6_ordinamento_controllo(df_conferimento)
    notify(6, f"Completato: {len(anomalie)} anomalie")

    # Salva output
    output_conferimento = output_dir / "conferimento_aggiornato.xlsx"
    salva_conferimento(df_conferimento, anomalie, output_conferimento, file_conferimento)

    output_anomalie = output_dir / "report_anomalie.xlsx"
    salva_report_anomalie(anomalie, output_anomalie)

    output_nuove = output_dir / "nuove_righe_conferimento.xlsx"
    salva_nuove_righe(df_nuove_righe, output_nuove)

    # Calcola statistiche
    col_z = _find_column(df_conferimento, ["incassato", "importo incassato"])

    fatture_incassate = 0
    if col_z:
        for _, row in df_conferimento.iterrows():
            val = _normalize_amount(row.get(col_z, 0))
            if val > 0:
                fatture_incassate += 1

    results = {
        "total_fatture": len(df_conferimento),
        "fatture_incassate": fatture_incassate,
        "anomalie": len(anomalie),
        "piani_rientro": piani_count,
        "nuove_righe": len(df_nuove_righe),
        "anomalie_detail": anomalie[:100],  # Max 100 per la UI
        "files": {
            "conferimento": str(output_conferimento),
            "anomalie": str(output_anomalie) if anomalie else None,
            "nuove_righe": str(output_nuove) if not df_nuove_righe.empty else None,
        },
    }

    logger.info("Elaborazione completata: %s", {
        k: v for k, v in results.items() if k not in ("anomalie_detail", "files")
    })
    return results
