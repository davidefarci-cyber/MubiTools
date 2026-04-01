"""Logica di business per il modulo Incassi Mubi.

Implementa le 7 fasi di elaborazione:
1. Conversione file Incassi (.txt -> DataFrame)
2. Cerca.Vert Importo Aperto (join con Massivo)
3. Piani di Rientro (join e annotazione)
4. Popola colonne Conferimento (Z, AA, AB)
5. Colonna 'Identico' e pulizia
6. Ordinamento e Controllo
7. Aggiornamento Pivot
"""

import logging
from collections.abc import Callable
from io import StringIO
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

    Rileva automaticamente il separatore (tab, punto e virgola, pipe).
    Normalizza date e importi.
    """
    logger.info("FASE 1: Parsing file incassi %s", file_path.name)

    raw_text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = [line for line in raw_text.splitlines() if line.strip()]
    candidate_separators = ["\t", ";", "|", ","]
    best_parse: tuple[int, str, int, pd.DataFrame] | None = None

    # Alcuni export Mubi includono righe descrittive iniziali:
    # proviamo vari separatori e offset, scegliendo il parse più stabile.
    max_offset = min(25, max(0, len(lines) - 1))
    for sep in candidate_separators:
        for offset in range(max_offset + 1):
            candidate_lines = lines[offset:]
            if not candidate_lines:
                continue
            if sep not in candidate_lines[0]:
                continue
            try:
                df_candidate = pd.read_csv(
                    StringIO("\n".join(candidate_lines)),
                    sep=sep,
                    dtype=str,
                    engine="python",
                )
            except Exception:
                continue
            if df_candidate.empty or len(df_candidate.columns) < 2:
                continue

            score = len(df_candidate.columns) * len(df_candidate)
            if best_parse is None or score > best_parse[0]:
                best_parse = (score, sep, offset, df_candidate)

    if best_parse is None:
        raise ValueError(
            "Impossibile interpretare il file incassi: formato non riconosciuto "
            "(separatore o intestazione non validi)."
        )

    _, sep, offset, df = best_parse
    logger.info("  Separatore rilevato: %r (header alla riga %d)", sep, offset + 1)

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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """JOIN tra incassi e file massivo su numero bolletta.

    Aggiunge colonna 'ImportoAperto' al DataFrame incassi.
    Identifica fatture con importo aperto positivo che nel conferimento
    erano negative (nuove righe da aggiungere).

    Returns:
        (df_incassi aggiornato, df_nuove_righe)
    """
    logger.info("FASE 2: Join con file massivo per ImportoAperto")

    df_massivo = pd.read_excel(file_massivo, dtype=str)
    df_massivo.columns = [c.strip() for c in df_massivo.columns]

    # Trova colonne chiave
    col_boll_incassi = _find_column(df_incassi, COL_NR_BOLLETTA_VARIANTS)
    col_boll_massivo = _find_column(df_massivo, COL_NR_BOLLETTA_VARIANTS)
    col_importo_massivo = _find_column(df_massivo, COL_IMPORTO_APERTO_VARIANTS)

    if not col_boll_incassi:
        raise ValueError("Colonna 'Nr. bolletta' non trovata nel file incassi")
    if not col_boll_massivo:
        raise ValueError("Colonna 'Numero bolletta' non trovata nel file massivo")

    # Normalizza importi nel massivo
    if col_importo_massivo:
        df_massivo[col_importo_massivo] = df_massivo[col_importo_massivo].apply(_normalize_amount)
    else:
        raise ValueError("Colonna 'Importo aperto' non trovata nel file massivo")

    # Join
    df_incassi["_join_key"] = df_incassi[col_boll_incassi].astype(str).str.strip()
    df_massivo["_join_key"] = df_massivo[col_boll_massivo].astype(str).str.strip()

    # Prendi solo le colonne necessarie dal massivo
    massivo_subset = df_massivo[["_join_key", col_importo_massivo]].drop_duplicates(
        subset=["_join_key"], keep="first"
    )
    massivo_subset = massivo_subset.rename(columns={col_importo_massivo: "ImportoAperto"})

    df_incassi = df_incassi.merge(massivo_subset, on="_join_key", how="left")
    df_incassi["ImportoAperto"] = df_incassi["ImportoAperto"].fillna(0.0)

    # Nuove righe: importo aperto positivo (nel conferimento erano negative)
    df_nuove = df_incassi[df_incassi["ImportoAperto"] > 0].copy()

    logger.info("  Join completato: %d righe, %d nuove righe da aggiungere",
                len(df_incassi), len(df_nuove))
    return df_incassi, df_nuove


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
    col_boll_piani = _find_column(df_piani, COL_NR_BOLLETTA_VARIANTS)

    if not col_boll_conf or not col_boll_piani:
        logger.warning("  Colonna numero bolletta non trovata, skip piani di rientro")
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
    """Cerca.Vert tra incassi e conferimento su numero bolletta.

    Popola:
    - Colonna Z (INCASSATO): importo aperto dalla fattura
    - Colonna AA (DATA PAGAMENTO): data pagamento dal file incassi
    - Colonna AB (MODALITA' DI PAGAMENTO): metodo pagamento dal file incassi
    """
    logger.info("FASE 4: Popola colonne Conferimento (Z, AA, AB)")

    col_boll_conf = _find_column(df_conferimento, COL_NR_BOLLETTA_VARIANTS)
    col_boll_inc = _find_column(df_incassi, COL_NR_BOLLETTA_VARIANTS)

    if not col_boll_conf or not col_boll_inc:
        raise ValueError("Colonna numero bolletta non trovata")

    # Prepara lookup da incassi
    col_importo = _find_column(df_incassi, COL_IMPORTO_APERTO_VARIANTS)
    col_data_pag = _find_column(df_incassi, COL_DATA_PAGAMENTO_VARIANTS)
    col_mod_pag = _find_column(df_incassi, COL_MODALITA_PAGAMENTO_VARIANTS)

    # Crea dizionario lookup
    lookup: dict[str, dict] = {}
    for _, row in df_incassi.iterrows():
        key = str(row[col_boll_inc]).strip()
        entry: dict = {}
        if col_importo and pd.notna(row.get("ImportoAperto")):
            entry["importo"] = row["ImportoAperto"]
        elif col_importo and pd.notna(row.get(col_importo)):
            entry["importo"] = _normalize_amount(row[col_importo])
        if col_data_pag and pd.notna(row.get(col_data_pag)):
            entry["data_pag"] = row[col_data_pag]
        if col_mod_pag and pd.notna(row.get(col_mod_pag)):
            entry["mod_pag"] = str(row[col_mod_pag])
        if entry:
            lookup[key] = entry

    # Trova colonne Z, AA, AB nel conferimento (per posizione o nome)
    # Prova prima per nome
    col_z = _find_column(df_conferimento, ["incassato", "importo incassato"])
    col_aa = _find_column(df_conferimento, COL_DATA_PAGAMENTO_VARIANTS)
    col_ab = _find_column(df_conferimento, COL_MODALITA_PAGAMENTO_VARIANTS)

    # Fallback: usa posizione colonne (Z=25, AA=26, AB=27)
    cols = list(df_conferimento.columns)
    if not col_z:
        col_z = cols[25] if len(cols) > 25 else None
    if not col_aa:
        col_aa = cols[26] if len(cols) > 26 else None
    if not col_ab:
        col_ab = cols[27] if len(cols) > 27 else None

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


# ─── FASE 5: Colonna Identico e pulizia ──────────────────────────

def fase5_identico(df_conferimento: pd.DataFrame) -> pd.DataFrame:
    """Confronto tra INCASSATO (col Z) e ImportoAffidato (col Q).

    Se identici -> fattura NON PAGATA -> azzera INCASSATO.
    """
    logger.info("FASE 5: Colonna Identico e pulizia")

    cols = list(df_conferimento.columns)

    # Colonna Q (posizione 16) = ImportoAffidato
    col_q = cols[16] if len(cols) > 16 else None
    # Colonna Z = INCASSATO
    col_z = _find_column(df_conferimento, ["incassato", "importo incassato"])
    if not col_z:
        col_z = cols[25] if len(cols) > 25 else None

    if not col_q or not col_z:
        logger.warning("  Colonne Q o Z non trovate, skip fase 5")
        return df_conferimento

    azzerati = 0
    for idx, row in df_conferimento.iterrows():
        val_z = _normalize_amount(row.get(col_z, 0))
        val_q = _normalize_amount(row.get(col_q, 0))

        if val_z != 0 and abs(val_z - val_q) < 0.01:
            # Importo identico = fattura non pagata
            df_conferimento.at[idx, col_z] = 0
            azzerati += 1

    logger.info("  Fatture non pagate (importo identico) azzerate: %d", azzerati)
    return df_conferimento


# ─── FASE 6: Ordinamento e Controllo ─────────────────────────────

def fase6_ordinamento_controllo(
    df_conferimento: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    """Ordina INCASSATO e genera report anomalie e correzioni.

    Returns:
        (df_conferimento_ordinato, anomalie, correzioni)
    """
    logger.info("FASE 6: Ordinamento e controllo")

    col_z = _find_column(df_conferimento, ["incassato", "importo incassato"])
    cols = list(df_conferimento.columns)
    if not col_z:
        col_z = cols[25] if len(cols) > 25 else None

    col_aa = _find_column(df_conferimento, COL_DATA_PAGAMENTO_VARIANTS)
    if not col_aa:
        col_aa = cols[26] if len(cols) > 26 else None

    col_ab = _find_column(df_conferimento, COL_MODALITA_PAGAMENTO_VARIANTS)
    if not col_ab:
        col_ab = cols[27] if len(cols) > 27 else None

    col_boll = _find_column(df_conferimento, COL_NR_BOLLETTA_VARIANTS)

    # Converti colonna Z in numerico per ordinamento
    if col_z:
        df_conferimento[col_z] = df_conferimento[col_z].apply(_normalize_amount)
        df_conferimento = df_conferimento.sort_values(by=col_z, ascending=True)

    anomalie: list[dict] = []
    correzioni: list[dict] = []

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

            # Fatture pagate (INCASSATO <= 0)
            if val_z <= 0:
                correzioni.append({
                    "numero_bolletta": boll,
                    "tipo": "fattura_pagata",
                    "dettaglio": f"INCASSATO = {val_z} (fattura pagata)",
                })

    logger.info("  Anomalie: %d, Correzioni: %d", len(anomalie), len(correzioni))
    return df_conferimento, anomalie, correzioni


# ─── FASE 7: Aggiornamento Pivot ─────────────────────────────────

def fase7_aggiorna_pivot(file_path: Path) -> str:
    """Verifica se il file contiene fogli pivot e notifica.

    Openpyxl non supporta l'aggiornamento automatico delle pivot table,
    quindi notifichiamo l'utente.
    """
    logger.info("FASE 7: Verifica pivot table")

    wb = load_workbook(file_path, data_only=False)
    pivot_sheets: list[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if hasattr(ws, "_pivots") and ws._pivots:
            pivot_sheets.append(sheet_name)

    wb.close()

    if pivot_sheets:
        msg = (
            f"Pivot table trovate nei fogli: {', '.join(pivot_sheets)}. "
            "Aprire il file in Excel e aggiornare manualmente le pivot (tasto destro > Aggiorna)."
        )
    else:
        msg = "Nessuna pivot table rilevata nel file."

    logger.info("  %s", msg)
    return msg


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
    """Esegue le 7 fasi di elaborazione e restituisce i risultati.

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
    notify(2, "Join con file massivo per ImportoAperto...")
    df_incassi, df_nuove_righe = fase2_join_importo_aperto(df_incassi, file_massivo)
    notify(2, f"Completato: {len(df_nuove_righe)} nuove righe")

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
    notify(5, "Confronto Identico e pulizia...")
    df_conferimento = fase5_identico(df_conferimento)
    notify(5, "Completato")

    # FASE 6
    notify(6, "Ordinamento e controllo...")
    df_conferimento, anomalie, correzioni = fase6_ordinamento_controllo(df_conferimento)
    notify(6, f"Completato: {len(anomalie)} anomalie, {len(correzioni)} correzioni")

    # FASE 7
    notify(7, "Verifica pivot table...")
    # Salva prima il file per poi verificare le pivot
    output_conferimento = output_dir / "conferimento_aggiornato.xlsx"
    salva_conferimento(df_conferimento, anomalie, output_conferimento, file_conferimento)
    pivot_msg = fase7_aggiorna_pivot(output_conferimento)
    notify(7, pivot_msg)

    # Salva report
    output_anomalie = output_dir / "report_anomalie.xlsx"
    salva_report_anomalie(anomalie, output_anomalie)

    output_nuove = output_dir / "nuove_righe_conferimento.xlsx"
    salva_nuove_righe(df_nuove_righe, output_nuove)

    # Calcola statistiche
    col_z = _find_column(df_conferimento, ["incassato", "importo incassato"])
    if not col_z:
        cols = list(df_conferimento.columns)
        col_z = cols[25] if len(cols) > 25 else None

    fatture_incassate = 0
    if col_z:
        for _, row in df_conferimento.iterrows():
            val = _normalize_amount(row.get(col_z, 0))
            if val < 0:
                fatture_incassate += 1

    results = {
        "total_fatture": len(df_conferimento),
        "fatture_incassate": fatture_incassate,
        "anomalie": len(anomalie),
        "piani_rientro": piani_count,
        "nuove_righe": len(df_nuove_righe),
        "pivot_message": pivot_msg,
        "anomalie_detail": anomalie[:100],  # Max 100 per la UI
        "correzioni_detail": correzioni[:100],
        "files": {
            "conferimento": str(output_conferimento),
            "anomalie": str(output_anomalie) if anomalie else None,
            "nuove_righe": str(output_nuove) if not df_nuove_righe.empty else None,
        },
    }

    logger.info("Elaborazione completata: %s", {
        k: v for k, v in results.items() if k not in ("anomalie_detail", "correzioni_detail", "files")
    })
    return results
