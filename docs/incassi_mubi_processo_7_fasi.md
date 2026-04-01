# Descrizione Dettagliata del Processo "Incassi Mubi" - 7 Fasi

> **Scopo del documento:** Descrivere esattamente cosa fa il codice attuale in ciascuna fase, affinché chi conosce il processo possa validare o correggere la logica. Le correzioni verranno poi usate per aggiornare il codice.

**File sorgente principale:** `app/modules/incassi_mubi/service.py`

---

## FILE DI INPUT

| # | Nome | Formato | Obbligatorio | Descrizione |
|---|------|---------|:---:|-------------|
| 1 | **File Incassi** | .txt / .csv | SI | Esportato da Mubi, contiene i dati degli incassi/insoluti |
| 2 | **File Massivo** (Estrazione Massiva) | .xlsx | SI | Estrazione massiva da Microsoft Dynamics |
| 3 | **File Conferimento** | .xlsx | SI | Il file conferimento da aggiornare (contiene molte colonne, pivot, ecc.) |
| 4 | **File Piani di Rientro** | .xlsx | NO | Lista fatture con piano di rientro attivo |

---

## FASE 1 — Conversione File Incassi
**Funzione:** `fase1_parse_incassi()`  
**Input:** File Incassi (.txt/.csv)  
**Output:** DataFrame `df_incassi`

### Cosa fa:
1. **Rileva automaticamente il separatore** del file (tab, punto e virgola, pipe, virgola) analizzando i primi 4096 byte
2. **Legge il file** come CSV con quel separatore (encoding UTF-8)
3. **Pulisce** i nomi delle colonne e i valori (rimuove spazi iniziali/finali)
4. **Normalizza gli importi** nelle colonne di tipo "importo aperto": rimuove `€`, punti (separatore migliaia), converte virgola in punto decimale, trasforma in numero float
5. **Normalizza le date** nelle colonne "data pagamento" e "data scadenza": converte in formato datetime con interpretazione giorno-prima (dd/mm/yyyy)

### Colonne cercate nel file incassi (con varianti):
- **Nr. Bolletta**: "nr. bolletta", "numero bolletta", "nr bolletta", "n. bolletta", "num bolletta", "nr.bolletta"
- **Importo Aperto**: "importo aperto", "importoaperto", "imp. aperto", "imp aperto"
- **Data Pagamento**: "data pagamento", "data pag.", "data pag", "datapagamento"
- **Modalita' di Pagamento**: "modalita' di pagamento", "modalita di pagamento", "mod. pagamento", "mod pagamento", "modalitapagamento"
- **Data Scadenza**: "data scadenza", "datascadenza", "data scad.", "scadenza"

---

## FASE 2 — Cerca.Vert Importo Aperto
**Funzione:** `fase2_join_importo_aperto()`  
**Input:** `df_incassi` (dalla Fase 1) + File Massivo (.xlsx)  
**Output:** `df_incassi` aggiornato + `df_nuove_righe`

### Cosa fa:
1. **Carica il File Massivo** (Excel) come stringhe
2. **Cerca la colonna "Nr. Bolletta"** sia nel file incassi che nel file massivo (usando le stesse varianti della Fase 1)
3. **Cerca la colonna "Importo Aperto"** nel file massivo e la normalizza a float
4. **Crea una chiave di join** basata sul numero bolletta (come stringa, senza spazi)
5. **Esegue un LEFT JOIN** tra `df_incassi` e il file massivo sulla chiave bolletta
   - Se ci sono duplicati nel massivo, tiene solo la prima occorrenza
   - Il risultato aggiunge la colonna **"ImportoAperto"** al df_incassi (valore dal massivo)
   - Se non trova match, ImportoAperto = 0.0
6. **Identifica le "nuove righe"**: tutte le righe di df_incassi dove `ImportoAperto > 0`
   - Queste vengono considerate "fatture con importo aperto positivo che nel conferimento erano negative" e vanno aggiunte al conferimento

### ⚠️ Domanda per la validazione:
- **La logica "nuove righe = ImportoAperto > 0" è corretta?** Il codice assume che un importo aperto positivo nel massivo significhi che la riga va aggiunta al conferimento. Questa logica è corretta nel contesto del processo reale?

---

## FASE 3 — Piani di Rientro
**Funzione:** `fase3_piani_rientro()`  
**Input:** `df_conferimento` (caricato dal File Conferimento .xlsx) + File Piani di Rientro (.xlsx, opzionale)  
**Output:** `df_conferimento` aggiornato + conteggio piani trovati

### Cosa fa:
1. **Se il file piani non è fornito**, salta questa fase
2. **Carica il File Piani di Rientro** (Excel)
3. **Cerca la colonna "Nr. Bolletta"** sia nel conferimento che nel file piani
4. **Crea un set** di tutti i numeri bolletta presenti nel file piani
5. **Per ogni riga del conferimento**, controlla se il numero bolletta è nel set dei piani:
   - Se SI → aggiunge il testo **"PIANO DI RIENTRO"** alla colonna **NOTE** del conferimento
   - Se la colonna NOTE non esiste, la crea
   - Non duplica l'annotazione se già presente

### Note:
- Il confronto è fatto riga per riga iterando su tutto il conferimento
- La colonna NOTE viene cercata in modo case-insensitive (cercando "NOTE" in maiuscolo)

---

## FASE 4 — Popola Colonne Conferimento
**Funzione:** `fase4_popola_conferimento()`  
**Input:** `df_conferimento` + `df_incassi` (aggiornato dalla Fase 2, con ImportoAperto)  
**Output:** `df_conferimento` aggiornato con colonne Z, AA, AB popolate

### Cosa fa:
1. **Cerca la colonna "Nr. Bolletta"** nel conferimento e negli incassi
2. **Cerca le colonne sorgente** nel df_incassi:
   - Colonna Importo Aperto (varianti: "importo aperto", ecc.)
   - Colonna Data Pagamento (varianti: "data pagamento", ecc.)
   - Colonna Modalita' di Pagamento (varianti: "modalita' di pagamento", ecc.)
3. **Crea un dizionario di lookup** dal df_incassi, indicizzato per numero bolletta:
   - Per il campo **"importo"**: usa la colonna `ImportoAperto` (quella aggiunta in Fase 2 dal massivo). Se non presente, fallback sulla colonna importo aperto originale del file incassi
   - Per il campo **"data_pag"**: usa la colonna data pagamento del file incassi
   - Per il campo **"mod_pag"**: usa la colonna modalita' di pagamento del file incassi
4. **Identifica le colonne target nel conferimento** (cerca per nome, poi per posizione):
   - **Colonna Z (posizione 25)** = "INCASSATO" o "importo incassato" → riceve il valore **importo** (ImportoAperto dal massivo)
   - **Colonna AA (posizione 26)** = "DATA PAGAMENTO" → riceve la **data pagamento** dal file incassi
   - **Colonna AB (posizione 27)** = "MODALITA' DI PAGAMENTO" → riceve la **modalita' pagamento** dal file incassi
   - Se le colonne non esistono, vengono create con i nomi sopra
5. **Per ogni riga del conferimento**, cerca il match nel dizionario per numero bolletta e popola le 3 colonne

### ⚠️ Domande per la validazione:
- **La colonna INCASSATO (Z) riceve l'ImportoAperto dal file massivo, NON un importo dal file incassi direttamente.** È corretto?
- **Le posizioni colonne (Z=25, AA=26, AB=27, contando da 0) sono corrette?** Corrispondono effettivamente alle colonne INCASSATO, DATA PAGAMENTO e MODALITA' DI PAGAMENTO nel file conferimento reale?

---

## FASE 5 — Colonna "Identico" e Pulizia
**Funzione:** `fase5_identico()`  
**Input:** `df_conferimento` (aggiornato dalla Fase 4)  
**Output:** `df_conferimento` con INCASSATO azzerato dove necessario

### Cosa fa:
1. **Identifica due colonne nel conferimento:**
   - **Colonna Q (posizione 16)** = "ImportoAffidato" (importo originariamente affidato)
   - **Colonna Z (posizione 25)** = "INCASSATO" (importo appena popolato nella Fase 4)
2. **Per ogni riga**, confronta i due valori:
   - Se INCASSATO (Z) ≠ 0 **E** la differenza tra INCASSATO e ImportoAffidato è inferiore a 0.01 (cioè sono sostanzialmente identici) →
   - **Azzera INCASSATO** (lo imposta a 0)
   - La logica è: se l'importo aperto è uguale all'importo affidato, significa che la fattura **NON è stata pagata** (l'intero importo è ancora aperto)

### ⚠️ Domande per la validazione:
- **La logica "importo aperto = importo affidato → fattura non pagata" è corretta?** Il ragionamento sembra essere: se tutto l'importo affidato è ancora aperto, allora non c'è stato nessun incasso e quindi INCASSATO va azzerato.
- **La colonna Q (posizione 16, contando da 0) è effettivamente "ImportoAffidato"?**

---

## FASE 6 — Ordinamento e Controllo
**Funzione:** `fase6_ordinamento_controllo()`  
**Input:** `df_conferimento` (dopo Fase 5)  
**Output:** `df_conferimento` ordinato + lista anomalie + lista correzioni

### Cosa fa:
1. **Converte la colonna INCASSATO (Z) in numerico** e **ordina** tutto il conferimento per INCASSATO in ordine crescente (prima le fatture non pagate / negative)
2. **Per ogni riga con INCASSATO ≠ 0**, controlla:
   - Se manca la **DATA PAGAMENTO** (colonna AA) → registra anomalia
   - Se manca la **MODALITA' DI PAGAMENTO** (colonna AB) → registra anomalia
3. **Genera due liste:**
   - **Anomalie** (tipo `dati_mancanti`): righe con INCASSATO diverso da zero ma senza data pagamento o modalità pagamento
   - **Correzioni** (tipo `fattura_pagata`): righe con INCASSATO ≤ 0

### ⚠️ Note:
- Le anomalie vengono poi usate per evidenziare le righe in ROSSO nel file Excel di output
- C'è una possibile incongruenza nel codice: il blocco "correzioni" è dentro al check `if val_z != 0`, ma cerca `val_z <= 0`. Questo significa che registra come "correzione" solo le righe con INCASSATO negativo (< 0), perché val_z = 0 non supera il check `val_z != 0`. **È questa la logica corretta?**

---

## FASE 7 — Aggiornamento Pivot
**Funzione:** `fase7_aggiorna_pivot()`  
**Input:** File conferimento aggiornato (già salvato su disco)  
**Output:** Messaggio informativo

### Cosa fa:
1. **Apre il file Excel** di output con openpyxl
2. **Scansiona tutti i fogli** alla ricerca di pivot table
3. **Se trova pivot table** → genera messaggio: "Pivot table trovate nei fogli: [nomi]. Aprire il file in Excel e aggiornare manualmente le pivot (tasto destro > Aggiorna)"
4. **Se non ne trova** → messaggio: "Nessuna pivot table rilevata nel file"

### Note:
- openpyxl NON può aggiornare automaticamente le pivot table
- L'utente deve farlo manualmente in Excel

---

## FILE DI OUTPUT

| File | Condizione | Contenuto |
|------|-----------|-----------|
| **conferimento_aggiornato.xlsx** | Sempre | Conferimento con colonne Z/AA/AB popolate, NOTE aggiornate, righe anomale in ROSSO |
| **report_anomalie.xlsx** | Se ci sono anomalie | Colonne: numero_bolletta, tipo, dettaglio |
| **nuove_righe_conferimento.xlsx** | Se ci sono nuove righe | Righe dal file incassi con ImportoAperto > 0 da aggiungere al conferimento |

---

## STATISTICHE CALCOLATE

| Statistica | Calcolo |
|------------|---------|
| **total_fatture** | Numero totale righe nel conferimento |
| **fatture_incassate** | Righe con INCASSATO < 0 (importo negativo = pagato) |
| **anomalie** | Conteggio anomalie (dati mancanti) |
| **piani_rientro** | Conteggio fatture con piano di rientro |
| **nuove_righe** | Righe con ImportoAperto > 0 da aggiungere |

### ⚠️ Domanda:
- **"fatture_incassate" conta le righe con INCASSATO < 0.** È corretto che un incasso sia rappresentato da un valore NEGATIVO? Oppure dovrebbe essere > 0?

---

## RIEPILOGO FLUSSO DATI

```
File Incassi (.txt)
       │
       ▼
   [FASE 1] Parse → df_incassi
       │
       ├── + File Massivo (.xlsx)
       ▼
   [FASE 2] Join su Nr. Bolletta → df_incassi + colonna ImportoAperto
       │                            → df_nuove_righe (ImportoAperto > 0)
       │
       │   File Conferimento (.xlsx) → df_conferimento
       │
       ├── + File Piani (.xlsx, opzionale)
       ▼
   [FASE 3] Annota "PIANO DI RIENTRO" in NOTE di df_conferimento
       │
       ▼
   [FASE 4] Cerca.Vert: per ogni bolletta in df_conferimento,
       │    cerca in df_incassi e popola:
       │      Col Z (INCASSATO) ← ImportoAperto (dal massivo via Fase 2)
       │      Col AA (DATA PAGAMENTO) ← data pagamento (dal file incassi)
       │      Col AB (MODALITA' PAGAMENTO) ← modalità (dal file incassi)
       │
       ▼
   [FASE 5] Se INCASSATO == ImportoAffidato (Col Q) → azzera INCASSATO
       │    (= fattura non pagata)
       │
       ▼
   [FASE 6] Ordina per INCASSATO crescente
       │    Verifica dati mancanti → anomalie
       │    Identifica INCASSATO ≤ 0 → correzioni
       │
       ▼
   [FASE 7] Controlla pivot table nel file Excel → messaggio utente
       │
       ▼
   OUTPUT: conferimento_aggiornato.xlsx
           report_anomalie.xlsx
           nuove_righe_conferimento.xlsx
```

---

## PUNTI DA VALIDARE (RIEPILOGO)

1. **Fase 2**: La logica "nuove righe = ImportoAperto > 0" è corretta?
2. **Fase 4**: INCASSATO (col Z) riceve l'ImportoAperto dal massivo — è corretto o dovrebbe ricevere un altro valore?
3. **Fase 4**: Le posizioni colonne Z=25, AA=26, AB=27, Q=16 (indice da 0) corrispondono al file conferimento reale?
4. **Fase 5**: La logica "ImportoAperto == ImportoAffidato → non pagata → azzera" è corretta?
5. **Fase 6**: La statistica "fatture_incassate = INCASSATO < 0" è corretta? Un incasso è negativo?
6. **Fase 6**: La logica delle "correzioni" (INCASSATO negativo dentro il blocco INCASSATO ≠ 0) — è il comportamento voluto?
7. **Generale**: Il dato "ImportoAperto" viene dal **file massivo**, non dal file incassi direttamente. La data e la modalità di pagamento vengono dal **file incassi**. È corretto questo split tra le due sorgenti?
