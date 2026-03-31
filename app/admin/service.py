"""Servizi admin: CRUD utenti, aggiornamenti da GitHub."""

import json
from datetime import datetime, timezone

import bcrypt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditLog, User


def hash_password(password: str) -> str:
    """Hash di una password con bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_user(
    db: Session,
    *,
    username: str,
    full_name: str,
    password: str,
    role: str = "user",
    allowed_modules: list[str] | None = None,
) -> User:
    """Crea un nuovo utente nel database."""
    if allowed_modules is None:
        allowed_modules = ["incassi_mubi"]
    user = User(
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role,
        allowed_modules=json.dumps(allowed_modules),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def ensure_admin_exists(db: Session) -> None:
    """Crea l'utente admin di default se il database è vuoto."""
    admin = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
    if admin is None:
        create_user(
            db,
            username=settings.ADMIN_USERNAME,
            full_name="Amministratore",
            password=settings.ADMIN_PASSWORD,
            role="admin",
            allowed_modules=["incassi_mubi"],
        )
        log = AuditLog(
            action="system_init",
            detail=json.dumps({"message": "Admin iniziale creato", "username": settings.ADMIN_USERNAME}),
            timestamp=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
