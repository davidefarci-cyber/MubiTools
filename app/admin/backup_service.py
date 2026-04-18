"""Servizi admin: backup/restore/reinit del database SQLite + listing backup.

Tutti i path passano da `settings.BACKUPS_DIR`. La gestione del lifecycle del
motore SQLAlchemy (`engine.dispose()`, `Base.metadata.create_all`) è
incapsulata qui per restore/reinit.
"""

import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.admin import service as admin_service
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import log_audit

logger = logging.getLogger(__name__)


_DB_PATH = Path(str(engine.url).replace("sqlite:///", ""))


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def get_db_path() -> Path:
    """Path al file SQLite del database corrente."""
    return _DB_PATH


def create_backup(
    db: Session,
    *,
    created_by_id: int | None = None,
) -> tuple[Path, str]:
    """Crea un backup consistente del DB SQLite (sqlite3 backup API).

    Returns:
        (path_assoluto_backup, filename).
    Raises:
        FileNotFoundError: se il file DB sorgente non esiste.
    """
    if not _DB_PATH.exists():
        raise FileNotFoundError("File database non trovato")

    settings.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"mubi_backup_{_timestamp()}.db"
    backup_path = settings.BACKUPS_DIR / filename

    src_conn = sqlite3.connect(str(_DB_PATH))
    dst_conn = sqlite3.connect(str(backup_path))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    log_audit(db, "db_backup", user_id=created_by_id, detail={"filename": filename})
    return backup_path, filename


def _validate_sqlite_file(path: Path) -> None:
    """Verifica che `path` sia un database SQLite valido. Solleva `ValueError`."""
    try:
        conn = sqlite3.connect(str(path))
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError(
            f"Il file caricato non e' un database SQLite valido: {exc}"
        ) from exc


def restore_database(
    db: Session,
    *,
    uploaded_filename: str,
    content: bytes,
    restored_by_id: int | None = None,
) -> str:
    """Sostituisce il DB corrente con il file caricato.

    Esegue prima un backup automatico `mubi_pre_restore_*.db`. Chiude la
    sessione corrente e dispone l'engine prima della sostituzione, poi
    ricrea le tabelle (no-op se già esistono).

    Returns:
        Nome del file di backup automatico.
    Raises:
        ValueError: se il file caricato non è un DB SQLite valido.
    """
    settings.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = settings.BACKUPS_DIR / "restore_upload.tmp"
    tmp_path.write_bytes(content)

    try:
        _validate_sqlite_file(tmp_path)
    except ValueError:
        tmp_path.unlink(missing_ok=True)
        raise

    log_audit(
        db, "db_restore",
        user_id=restored_by_id,
        detail={"uploaded_filename": uploaded_filename},
    )

    auto_backup_name = f"mubi_pre_restore_{_timestamp()}.db"
    auto_backup_path = settings.BACKUPS_DIR / auto_backup_name
    if _DB_PATH.exists():
        shutil.copy2(str(_DB_PATH), str(auto_backup_path))

    db.close()
    engine.dispose()

    shutil.move(str(tmp_path), str(_DB_PATH))

    Base.metadata.create_all(bind=engine)

    return auto_backup_name


def reinit_database(*, triggered_by_username: str) -> str:
    """Esegue il reset completo del DB (drop + create tutte le tabelle).

    Esegue un backup automatico `mubi_pre_reinit_*.db`, poi ricrea l'utente
    admin di default (altrimenti il DB resterebbe inaccessibile fino al
    prossimo restart). Apre una nuova sessione perché quella del chiamante
    viene chiusa con `engine.dispose()`.

    Returns:
        Nome del file di backup automatico.
    """
    settings.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    auto_backup_name = f"mubi_pre_reinit_{_timestamp()}.db"
    auto_backup_path = settings.BACKUPS_DIR / auto_backup_name
    if _DB_PATH.exists():
        shutil.copy2(str(_DB_PATH), str(auto_backup_path))

    engine.dispose()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    new_db = SessionLocal()
    try:
        admin_service.ensure_admin_exists(new_db)
        log_audit(
            new_db, "db_reinit",
            user_id=None,
            detail={
                "auto_backup": auto_backup_name,
                "triggered_by": triggered_by_username,
            },
        )
    finally:
        new_db.close()

    return auto_backup_name


def list_recent_backups(limit: int = 10) -> list[str]:
    """Restituisce i nomi dei backup più recenti (ordinati desc)."""
    if not settings.BACKUPS_DIR.exists():
        return []
    files = sorted(
        [f.name for f in settings.BACKUPS_DIR.glob("*.db")],
        reverse=True,
    )
    return files[:limit]
