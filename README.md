# MUBI Tools

Web application centralizzata per l'automazione di procedure operative su file Excel esportati da Microsoft Dynamics (Mubi).

## Funzionalità

- **Autenticazione** multi-utente con ruoli (admin/user)
- **Modulo Incassi Mubi** — elaborazione automatica file incassi/conferimento
- **Pannello Admin** — gestione utenti, aggiornamenti, audit log
- **Aggiornamenti automatici** da GitHub

## Stack Tecnologico

- **Backend**: Python 3.11+ / FastAPI
- **Frontend**: HTML5 + CSS3 + JavaScript vanilla
- **Database**: SQLite (migrabile a PostgreSQL)
- **Auth**: JWT (python-jose + bcrypt)
- **Excel**: pandas + openpyxl

## Installazione

Vedere `install/setup.bat` per l'installazione automatica su Windows Server.

## Sviluppo

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
cp .env.example .env      # Configurare le variabili
uvicorn app.main:app --reload --port 8000
```
