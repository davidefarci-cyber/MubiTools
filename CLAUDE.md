# CLAUDE.md — Grid

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
├── shared/              # Utility condivise tra moduli
│   ├── excel_mapper.py  # find_column(df, candidates, *, mode)
│   ├── regex.py         # EMAIL_REGEX, is_valid_email
│   └── constants.py     # SMTP_HOST/PORT/SEND_TIMEOUT/TEST_TIMEOUT
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

Ogni `app/modules/<nome>/__init__.py` re-esporta il router:
`from .router import router; __all__ = ["router"]`.
`app/main.py` importa con `from app.modules.<nome> import router as ...`.

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

## app/shared/ — utility condivise

Package di utility senza dipendenze da FastAPI/DB, importabile da qualsiasi modulo.

- **`excel_mapper.py`** — `find_column(df, candidates, *, mode="exact")`:
  trova il nome colonna reale nel DataFrame tra i candidati.
  - `mode="exact"` (default): match esatto case-insensitive dopo strip.
  - `mode="substring"`: il candidato è contenuto nel nome colonna (case-insensitive).
  I `COL_*_VARIANTS` restano nei moduli che li definiscono (dati business specifici);
  vengono passati come `candidates` a `find_column`.
- **`regex.py`** — `EMAIL_REGEX` e `is_valid_email(address)`: unica sorgente
  di verità per il formato email/PEC. Importare da qui, non ridefinire localmente.
- **`constants.py`** — costanti globali non business-specific:
  `SMTP_HOST`, `SMTP_PORT`, `SMTP_SEND_TIMEOUT` (invio PEC),
  `SMTP_TEST_TIMEOUT` (test login admin).
  Aggiungere qui nuovi magic value ricorrenti tra ≥ 2 moduli.

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
3. In `app/main.py` importare il router con
   `from app.modules.<nome> import router as <nome>_router` e montarlo con
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
  `app.shared.regex.is_valid_email`), sync pratiche pending ↔ anagrafica,
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
- **`email_service.py`** — `send_pec(...)` su SMTP Aruba (parametri da
  `app.shared.constants`). `EMAIL_REGEX` e `is_valid_email()` vivono in
  `app/shared/regex.py` e sono importati da qui.
- **`settings_service.py`** — persistenza JSON delle impostazioni
  (`data/remi_settings.json`) + salvataggio/lettura del template DOCX
  (`data/remi_template.docx`).

## Modulo `admin`

Il pannello admin segue lo stesso pattern `router → service` con split per
dominio (utenti/audit, PEC, backup DB). Il router resta thin: auth, parsing,
mapping `ValueError`→`HTTPException`, response shape.

- **`router.py`** — solo orchestrazione: `Depends(require_admin)`, parsing
  request, delega ai service, formattazione response (`_user_to_dict`,
  `_pec_to_dict`).
- **`schemas.py`** — modelli Pydantic di request/response (`UserOut`,
  `CreateUserRequest`, `UpdateUserRequest`, `ResetPasswordRequest`,
  `ApplyUpdateRequest`, `AuditLogOut`, `CreatePecRequest`, `UpdatePecRequest`).
- **`service.py`** — User CRUD (`create_user`, `update_user`, `reset_password`,
  `list_users`, getters), password hashing/verifica bcrypt
  (`hash_password`/`verify_password`, usato anche da `app/auth/router.py`),
  audit log (`get_audit_log` paginato, `delete_audit_log`),
  `ensure_admin_exists` (chiamato da `app/main.py` in lifespan).
- **`pec_service.py`** — CRUD account PEC + test SMTP (parametri SMTP
  da `app.shared.constants`). Gestisce dup-check email, encrypt/decrypt
  password via `app/utils/encryption.py`, e protezione "ultima PEC attiva"
  (errore di dominio sollevato come `ValueError`). `test_pec_smtp` è puro:
  ritorna `(success, error_msg)` senza audit, è il router a loggare
  `pec_test_ok`/`pec_test_fail`.
- **`backup_service.py`** — backup/restore/reinit del DB SQLite via
  `sqlite3.backup` API + `shutil`. Usa `settings.BACKUPS_DIR` come unica
  sorgente di path. Restore e reinit incapsulano il lifecycle del motore
  SQLAlchemy (`engine.dispose()` + `Base.metadata.create_all`); il reinit
  apre una nuova `SessionLocal` per ricreare l'utente admin via
  `service.ensure_admin_exists` (altrimenti il DB resterebbe inaccessibile).
  Backup automatici `pre_restore_*.db` / `pre_reinit_*.db` salvati prima di
  ogni operazione distruttiva.
- **`update_service.py`** — **isolato e intoccato**. Gestisce esclusivamente
  gli aggiornamenti GitHub: `git fetch/pull` via GitPython, `pip install -r
  requirements.txt`, restart servizio (systemd/sc su Windows). Nessuna
  interazione DB. Non rifattorizzare insieme a router/business logic.

## Modulo `caricamento_remi`

Modulo "JSON-in, JSON-out": il parsing del file `.xlsx` delle pratiche REMI
avviene interamente lato **frontend** (JavaScript in `app/static/`), il
backend riceve righe strutturate via schemi Pydantic. Router thin, tutta la
logica di dominio è nel service.

- **`router.py`** — solo orchestrazione HTTP: `Depends(require_module(...))`,
  parsing richieste Pydantic, `log_audit`, logging, mapping
  `ValueError`→`HTTPException(400)`. Nessuna query SQL né state machine.
- **`service.py`** — tutta la logica di dominio:
  - `match_vat_numbers(rows, db)` — lookup P.IVA in `DlRegistry` attivi.
  - `create_practices_batch(data, db)` — inserisce pratiche (scarta righe
    senza `company_name`), genera `batch_id` UUID, `db.commit()`.
  - `list_practice_history(db, filtri…, page, page_size)` — query con
    filtri (status/vat/search/date range), aggregazione per
    `(vat_number, effective_date, batch_id)`, state machine di gruppo con
    priorità `error > pending > cancelled > sent`, paginazione in memoria.
  - `get_practices_stats(db)` — conteggi per status + `last_send_date`.
  - `reset_practices_to_pending(ids, db)` — resetta pratiche `error` a
    `pending` (azzera `error_detail`/`send_batch_id`/`sent_at`).
  - `transition_practices_status(ids, new_status, db)` — transizioni
    validate da `_ALLOWED_TRANSITIONS`; solleva `ValueError` su stato
    destinazione non ammesso.
  - `validate_partita_iva(piva)` — checksum standard italiano, riusata
    anche da `invio_remi.service` (unica sorgente di verità).
- **`schemas.py`** — modelli Pydantic per match/confirm/history/stats/
  resend/change-status.

## Modulo `incassi_mubi`

Modulo file-heavy: riceve upload `.xlsx`/`.txt`, esegue una pipeline a 6
fasi in un thread separato con progress callback, produce file di output
scaricabili. Il `service.py` monolitico è stato suddiviso in quattro file
per responsabilità; l'unico simbolo importato dal router è `elabora_incassi`.

- **`router.py`** — upload file, orchestrazione job async (thread + callback
  progress in memoria), download output. Unico import dal service:
  `elabora_incassi`.
- **`service.py`** — orchestratore `elabora_incassi`: chiama `fase1`→`fase6`
  in sequenza con `progress_callback`, fa validazione anticipata delle
  colonne via `_validate_all_columns`, salva i file di output. Contiene
  anche `salva_conferimento` (con highlight anomalie in rosso via
  `RED_FILL`), `salva_report_anomalie`, `salva_nuove_righe`.
- **`processor.py`** — le 6 fasi del pipeline Excel (`fase1_parse_incassi`
  → `fase6_ordinamento_controllo`). **Modificare qui per cambiare la logica
  di una fase esistente o aggiungere una nuova fase** (poi registrarla in
  `elabora_incassi`).
- **`excel_reader.py`** — lettura smart di file Excel (`_read_excel_smart`
  auto-rileva il foglio giusto provando tutti i fogli finché trova le
  colonne attese) + costanti `COL_*_VARIANTS` (varianti case-insensitive
  del nome colonna, passate a `app.shared.excel_mapper.find_column`).
  **Modificare qui per supportare un nuovo formato Excel** (aggiungere
  varianti) o un nuovo file sorgente.
- **`validator.py`** — normalizzazione valori (`_normalize_amount`:
  gestisce `€`/virgole/separatori di migliaia; `_normalize_date`:
  `dayfirst=True`) e data-quality check `_validate_all_columns` sulle
  colonne richieste. **Modificare qui per aggiungere una regola di
  validazione o gestire un formato valore atipico**.
- **`schemas.py`** — modelli Pydantic per upload/process/result.

Il column-mapping usa `find_column` da `app/shared/excel_mapper.py`;
i `COL_*_VARIANTS` sono dati business del modulo, non spostati in shared.

## Note operative

- `ADMIN_PASSWORD` è **required**: pydantic-settings fallisce l'avvio se manca.
- Password PEC e altri secret passano da `app/utils/encryption.py` (Fernet,
  chiave auto-generata in `data/secret.key`).
- Path sempre via `settings` o `BASE_DIR` — mai ricalcolare `Path(__file__)`.
- Aggiornamenti: `app/admin/update_service.py` usa GitPython sul working tree
  locale (`BASE_DIR`). Non installare Grid come package Python.
- `tools/legacy/` contiene utility standalone non integrate (es. Tkinter GUI
  Windows). Ignorare in dev normale.
