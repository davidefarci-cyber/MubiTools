# Grid

Web application per l'automazione delle procedure operative di backoffice di un'azienda di vendita di energia elettrica e gas. Elabora file Excel esportati da Microsoft Dynamics, genera pratiche REMI, invia PEC ai distributori.

## Funzionalità

- **Autenticazione** multi-utente con ruoli (admin/user) e permessi per modulo
- **Incassi** — elaborazione automatica di file incassi / conferimento / piani
- **Connessione** — trasformazione Excel per attività di connessione gas
- **Caricamento REMI** — upload pratiche REMI con validazione P.IVA
- **Invio REMI** — generazione PDF + invio PEC massivo ai distributori
- **Pannello Admin** — utenti, PEC, backup DB, aggiornamenti da GitHub, audit log

## Stack

- **Backend**: Python 3.11+ / FastAPI / SQLAlchemy 2.x / Pydantic v2
- **Frontend**: HTML + CSS + JavaScript vanilla (no framework)
- **Database**: SQLite (`database/app.db`)
- **Auth**: JWT (`python-jose` + `bcrypt`)
- **Excel**: pandas + openpyxl
- **PDF**: `python-docx` + LibreOffice (`soffice --headless`)

## Installazione

Vedere `install/setup.bat` per l'installazione automatica su Windows Server (richiede LibreOffice e NSSM).

## Sviluppo

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # Impostare ADMIN_PASSWORD (obbligatorio)
uvicorn app.main:app --reload --port 8000
```

Test:

```bash
pytest -q
```

## Documentazione

Convenzioni di codice e layout del repo: vedi `CLAUDE.md`.
