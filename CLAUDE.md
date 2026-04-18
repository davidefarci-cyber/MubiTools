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

Esiste una test suite smoke minima in `tests/`. Stack: `pytest` +
`pytest-asyncio` + `httpx` (via `fastapi.testclient.TestClient`). Config in
`pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`).

Comando: `pytest -q` dalla root del repo.

### Struttura

```
tests/
├── __init__.py
├── conftest.py         # fixture: client, auth_headers; env setup pre-import
├── test_health.py      # GET /health
├── test_auth.py        # login wrong/ok, /auth/first-boot pubblico
├── test_admin.py       # /admin/users senza/con auth
└── modules/
    ├── __init__.py
    ├── test_incassi_mubi.py
    ├── test_connessione.py
    ├── test_invio_remi.py
    ├── test_caricamento_remi.py
    └── test_caricamento_remi_validate.py  # unit pura su validate_partita_iva
```

Regola di naming: i file di test sono mirror del path in `app/` (es. un
futuro test per `app/modules/incassi_mubi/service.py` va in
`tests/modules/incassi_mubi/test_service.py`).

### Fixture (in `tests/conftest.py`)

- `client` — `TestClient(app)` con `lifespan` attivo (crea tabelle + admin).
  Scope: session.
- `auth_headers` — header `Authorization: Bearer <jwt>` per l'admin di test.
  Scope: session.

Setup env **prima** di importare `app.*`:
- `ADMIN_PASSWORD=testadmin123` (required da `Settings`);
- `DATABASE_URL` → SQLite su tempfile (pulito a fine sessione).

Motivo: `app.config.settings` è istanziato a import time e
`app.database.engine` è creato dal valore di `settings.DATABASE_URL` a module
load. Le env vars vanno settate nel top di `conftest.py`, prima di ogni
`from app...`.

### Convenzioni

- Endpoint senza Authorization header → asserire `status_code in (401, 403)`:
  `HTTPBearer(auto_error=True)` di FastAPI risponde **403** quando l'header
  manca, mentre `get_current_user` risponde **401** su token invalido.
- Oggi la suite è volutamente smoke-only (scope: garantire che l'app si
  avvii e che gli endpoint protetti rifiutino richieste anonime). Test più
  granulari su parsing Excel / PDF / PEC verranno aggiunti dopo i refactor.

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

## Modulo `invio_remi`

Esempio di modulo con sottosistemi multipli: il file `service.py` orchestra la
business logic e delega a service specializzati per le capability trasversali
(PDF, PEC, impostazioni su disco).

- **`router.py`** — solo routing: auth, parsing `Form`/`UploadFile`,
  `StreamingResponse` per l'SSE di `/send-all`, delega a `service`.
- **`service.py`** — CRUD anagrafica DL (con validazione P.IVA tramite
  `caricamento_remi.service.validate_partita_iva` + formato PEC tramite
  `email_service.is_valid_email`), sync pratiche pending ↔ anagrafica,
  aggregazione pending per distributore, orchestrazione `stream_send_all`
  (async generator che yielda eventi SSE: `generating_pdf`, `sending`,
  `sent`/`error`, `complete`). Gli errori di dominio sono segnalati con
  `HTTPException` per mantenere thin il router (deroga consapevole alla
  regola "no FastAPI nei service").
- **`pdf_service.py`** — `generate_pdf(...)`: apre il template DOCX,
  sostituisce i tag (`<NOME_DL>`, `<PEC_DL>`, `<DATA_DECORRENZA>`, `<DATA>`,
  `<REMI>` come tabella), converte in PDF via `soffice --headless` e
  restituisce bytes. Usa `python-docx` + OPC XML per la tabella REMI.
  Richiede LibreOffice/Writer installato (`soffice` nel PATH).
- **`email_service.py`** — `send_pec(...)` su `smtps.pec.aruba.it:465`
  (SMTP_SSL + `smtplib`). Contiene anche `EMAIL_REGEX` e `is_valid_email()`:
  unica sorgente di verità per il formato email/PEC nel modulo (la
  centralizzazione in `app/shared/` è prevista in una sessione futura).
- **`settings_service.py`** — persistenza JSON delle impostazioni
  (`data/remi_settings.json`) + salvataggio/lettura del template DOCX
  (`data/remi_template.docx`).

## Note operative

- `ADMIN_PASSWORD` è **required**: pydantic-settings fallisce l'avvio se manca.
- Password PEC e altri secret passano da `app/utils/encryption.py` (Fernet,
  chiave auto-generata in `data/secret.key`).
- Path sempre via `settings` o `BASE_DIR` — mai ricalcolare `Path(__file__)`.
- Aggiornamenti: `app/admin/update_service.py` usa GitPython sul working tree
  locale (`BASE_DIR`). Non installare MubiTools come package.
- `tools/legacy/` contiene utility standalone non integrate (es. Tkinter GUI
  Windows). Ignorare in dev normale.
