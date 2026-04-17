# CLAUDE.md — MUBI Tools

Guida sintetica per navigare il repo e aggiungere codice coerente con le
convenzioni esistenti. Per dettagli di business consultare i singoli moduli.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy 2.x, Pydantic v2 (+ pydantic-settings)
- SQLite (`database/app.db`), JWT (`python-jose` + `bcrypt`)
- Frontend: static HTML/CSS/JS in `app/static/` (no framework)

## Layout repository

```
app/
├── main.py              # Entrypoint FastAPI: lifespan, middleware, router mount, exception handler globale
├── config.py            # Settings pydantic + BASE_DIR/STATIC_DIR/BACKUPS_DIR/UPLOAD_DIR/LOG_DIR
├── database.py          # Engine + SessionLocal + Base + get_db dependency
├── models.py            # Tutti i modelli SQLAlchemy (User, AuditLog, PecAccount, DlRegistry, RemiPractice, …)
├── logging_config.py    # setup_logging(): rotating file + console
├── auth/                # JWT, dipendenze FastAPI (get_current_user, require_admin, require_module), rate limit
├── admin/               # Pannello admin: utenti, update via GitPython, backup/restore DB, audit
├── utils/               # Helper condivisi (encryption.py per Fernet)
├── modules/             # Un package per modulo di business
│   ├── caricamento_remi/
│   ├── invio_remi/
│   ├── incassi_mubi/
│   └── connessione/
└── static/              # SPA statica servita da FastAPI
data/uploads, data/backups, database/, logs/, scripts/, install/, tools/legacy/
```

## Convenzione modulo: `router → service → schemas`

Ogni modulo di business in `app/modules/<nome>/` espone tre file:

- **`router.py`** — `APIRouter()` con endpoint thin. Responsabilità:
  validazione input via schemas, dependency injection (`get_db`,
  `require_module(MODULE_NAME)`), chiamata ai service, logging, `log_audit`.
  Niente SQL raw né logica di dominio.
- **`service.py`** — funzioni pure o funzioni che operano su `Session`.
  Contengono la logica di business (parsing Excel, generazione XML/PDF,
  aggregazioni, validazioni di dominio). Nessun riferimento a FastAPI.
- **`schemas.py`** — modelli Pydantic per request/response. Niente logica.

Moduli con sottosistemi multipli (es. `invio_remi`) possono avere più
file service affiancati (`email_service.py`, `pdf_service.py`,
`settings_service.py`): stesso principio, split per responsabilità.

## Shared / infrastruttura

- **Config** → `app/config.py`. Accesso: `from app.config import settings`
  (e `BASE_DIR` se serve il path del repo). Aggiungere nuovi attributi a
  `Settings`; i path derivati stanno qui (non ricalcolarli con
  `Path(__file__)…`).
- **Auth** → `app/auth/dependencies.py`:
  - `get_current_user` — JWT valido, utente attivo
  - `require_admin` — richiede `role == "admin"`
  - `require_module("<nome>")` — factory: restituisce una dependency che
    verifica `user.has_module(<nome>)`. Usare **sempre** questa invece di
    duplicare il check.
- **DB** → `from app.database import get_db`. Commit espliciti nel service
  o nel router (no autocommit).
- **Modelli** → un solo file `app/models.py`. `log_audit(db, action, user_id, detail)` per tracciare azioni.
- **Logging** → `logger = logging.getLogger(__name__)` in ogni modulo.
  Non usare `print`. Exception non gestite sono loggate con traceback dall'handler globale in `app/main.py`.

## Esecuzione in dev

Serve un `.env` con almeno `ADMIN_PASSWORD=...` (obbligatorio, fail-fast se
mancante). Partendo da `.env.example`:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # editare ADMIN_PASSWORD
uvicorn app.main:app --reload --port 8000
curl http://127.0.0.1:8000/health
```

## Test

**Al momento non esiste una test suite.** Quando si iniziano a scrivere test:

- Directory `tests/` nella root, mirror della struttura `app/`
  (`tests/modules/caricamento_remi/test_service.py`, ecc.).
- Stack suggerito: `pytest` + `httpx.AsyncClient` / `TestClient` FastAPI +
  SQLite in-memory (override `get_db` con una fixture).
- Aggiungere `pytest` a `requirements.txt` (o a un `requirements-dev.txt`).
- Comando: `pytest -q` dalla root.

Finché non c'è suite, la verifica minima manuale è:

```bash
ADMIN_PASSWORD=test python -c "from app.main import app; print('OK')"
ADMIN_PASSWORD=test uvicorn app.main:app --port 8765 &
curl -s http://127.0.0.1:8765/health
```

## Aggiungere un nuovo modulo

1. Creare `app/modules/<nome>/` con `__init__.py`, `router.py`, `service.py`, `schemas.py`.
2. In `router.py`:
   - `router = APIRouter()`
   - `MODULE_NAME = "<nome>"`
   - endpoint con `current_user: User = Depends(require_module(MODULE_NAME))`
     quando l'accesso va filtrato per modulo abilitato.
3. In `app/main.py` importare il router e chiamare
   `app.include_router(<nome>_router, prefix="/api/<nome-kebab>", tags=["<nome>"])`.
4. Se il modulo ha una UI, aggiungere la pagina in `app/static/` e il link nel menu SPA.
5. Se introduce nuovi modelli DB, definirli in `app/models.py` (non creare
   file separati): `Base.metadata.create_all` in `lifespan` crea le tabelle all'avvio.
6. Permessi per utente: il modulo va aggiunto alla lista `modules` del `User`
   — vedi la logica in `lifespan` di `app/main.py` che auto-aggiunge `connessione` agli utenti esistenti, come riferimento.
7. Pattern audit log: in ogni azione significativa chiamare
   `log_audit(db, "<azione>", user_id=current_user.id, detail={...})`.

## Note operative

- `ADMIN_PASSWORD` è **required**: pydantic-settings fallisce l'avvio se manca.
- Password PEC e altri secret passano da `app/utils/encryption.py` (Fernet,
  chiave auto-generata in `data/secret.key`).
- Path sempre via `settings` o `BASE_DIR` — mai ricalcolare `Path(__file__)`.
- Aggiornamenti: `app/admin/update_service.py` usa GitPython sul working tree
  locale (`BASE_DIR`). Non installare MubiTools come package.
- `tools/legacy/` contiene utility standalone non integrate (es. Tkinter GUI
  Windows). Ignorare in dev normale.
