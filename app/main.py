"""MUBI Tools — FastAPI entrypoint."""

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.logging_config import setup_logging
from app.auth.router import router as auth_router
from app.admin.router import router as admin_router
from app.modules.incassi_mubi.router import router as incassi_router
from app.modules.connessione.router import router as connessione_router
from app.modules.invio_remi.router import router as invio_remi_router
from app.modules.caricamento_remi.router import router as caricamento_remi_router
from app.admin.service import ensure_admin_exists

logger = logging.getLogger(__name__)

START_TIME: float = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Crea le tabelle del database e le cartelle necessarie all'avvio."""
    # Setup logging
    setup_logging()
    logger.info("MUBI Tools v%s — avvio in corso", settings.version)

    # Crea cartelle se non esistono
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Crea tabelle database
    Base.metadata.create_all(bind=engine)
    logger.info("Database inizializzato: %s", settings.DATABASE_URL)

    # Crea utente admin di default se DB vuoto + aggiorna moduli utenti esistenti
    db = SessionLocal()
    try:
        ensure_admin_exists(db)

        # Aggiungi modulo 'connessione' agli utenti che non ce l'hanno
        from app.models import User
        users = db.query(User).all()
        for user in users:
            modules = user.get_modules()
            if "connessione" not in modules:
                modules.append("connessione")
                user.set_modules(modules)
        db.commit()
    finally:
        db.close()

    logger.info("Servizio pronto su porta %d", settings.PORT)
    yield
    logger.info("MUBI Tools — shutdown")


app = FastAPI(
    title="MUBI Tools",
    description="Gestione automatizzata procedure operative su file Excel da Microsoft Dynamics",
    version=settings.version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In produzione: limitare agli IP del server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router API
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(incassi_router, prefix="/api/incassi", tags=["incassi"])
app.include_router(connessione_router, prefix="/api/connessione", tags=["connessione"])
app.include_router(invio_remi_router, prefix="/api/invio-remi", tags=["invio-remi"])
app.include_router(caricamento_remi_router, prefix="/api/caricamento-remi", tags=["caricamento-remi"])

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Logga le eccezioni non gestite con traceback e risponde 500 generico."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# File statici
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")


@app.get("/health")
async def health_check() -> JSONResponse:
    """Stato del servizio, versione e uptime."""
    uptime_seconds = int(time.time() - START_TIME)
    return JSONResponse(
        content={
            "status": "ok",
            "version": settings.version,
            "uptime_seconds": uptime_seconds,
        }
    )


@app.get("/")
async def root() -> JSONResponse:
    """Redirect alla SPA."""
    from fastapi.responses import FileResponse

    return FileResponse(settings.STATIC_DIR / "index.html")
