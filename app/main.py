"""MUBI Tools — FastAPI entrypoint."""

import logging
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.logging_config import setup_logging
from app.auth.router import router as auth_router
from app.admin.router import router as admin_router
from app.modules.incassi_mubi.router import router as incassi_router
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

    # Crea utente admin di default se DB vuoto
    db = SessionLocal()
    try:
        ensure_admin_exists(db)
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

# File statici
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


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

    return FileResponse(static_dir / "index.html")
