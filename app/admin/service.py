"""Servizi admin: CRUD utenti, aggiornamenti da GitHub."""

import json
from datetime import datetime, timezone

import bcrypt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditLog, User, log_audit


def hash_password(password: str) -> str:
    """Hash di una password con bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una password contro il suo hash bcrypt."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_user(
    db: Session,
    *,
    username: str,
    full_name: str,
    password: str,
    role: str = "user",
    allowed_modules: list[str] | None = None,
    created_by_id: int | None = None,
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

    log_audit(
        db,
        "user_created",
        user_id=created_by_id,
        detail={"username": username, "role": role, "modules": allowed_modules},
    )
    return user


def update_user(
    db: Session,
    *,
    user: User,
    full_name: str | None = None,
    role: str | None = None,
    allowed_modules: list[str] | None = None,
    is_active: bool | None = None,
    updated_by_id: int | None = None,
) -> User:
    """Aggiorna i dati di un utente esistente."""
    changes: dict[str, str] = {}

    if full_name is not None and full_name != user.full_name:
        user.full_name = full_name
        changes["full_name"] = full_name

    if role is not None and role != user.role:
        user.role = role
        changes["role"] = role

    if allowed_modules is not None:
        user.set_modules(allowed_modules)
        changes["allowed_modules"] = json.dumps(allowed_modules)

    if is_active is not None and is_active != user.is_active:
        user.is_active = is_active
        changes["is_active"] = str(is_active)

    if changes:
        db.commit()
        db.refresh(user)
        log_audit(
            db,
            "user_updated",
            user_id=updated_by_id,
            detail={"target_username": user.username, "changes": changes},
        )

    return user


def reset_password(
    db: Session,
    *,
    user: User,
    new_password: str,
    reset_by_id: int | None = None,
) -> None:
    """Resetta la password di un utente."""
    user.hashed_password = hash_password(new_password)
    db.commit()

    log_audit(
        db,
        "password_reset",
        user_id=reset_by_id,
        detail={"target_username": user.username},
    )


def toggle_user_active(
    db: Session,
    *,
    user: User,
    toggled_by_id: int | None = None,
) -> User:
    """Attiva/disattiva un utente."""
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)

    log_audit(
        db,
        "user_toggled",
        user_id=toggled_by_id,
        detail={
            "target_username": user.username,
            "is_active": user.is_active,
        },
    )
    return user


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Trova un utente per ID."""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> User | None:
    """Trova un utente per username."""
    return db.query(User).filter(User.username == username).first()


def list_users(db: Session) -> list[User]:
    """Restituisce tutti gli utenti ordinati per username."""
    return db.query(User).order_by(User.username).all()


def get_audit_log(
    db: Session,
    *,
    page: int = 1,
    per_page: int = 50,
    action_filter: str | None = None,
    user_id_filter: int | None = None,
) -> tuple[list[AuditLog], int]:
    """Restituisce l'audit log paginato con filtri opzionali.

    Returns:
        Tupla (lista_log, totale_record).
    """
    query = db.query(AuditLog)

    if action_filter:
        query = query.filter(AuditLog.action == action_filter)
    if user_id_filter is not None:
        query = query.filter(AuditLog.user_id == user_id_filter)

    total = query.count()
    logs = (
        query
        .order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return logs, total


def ensure_admin_exists(db: Session) -> None:
    """Crea l'utente admin di default se il database è vuoto."""
    admin = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
    if admin is None:
        user = User(
            username=settings.ADMIN_USERNAME,
            full_name="Amministratore",
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            role="admin",
            allowed_modules=json.dumps(["incassi_mubi"]),
        )
        db.add(user)
        db.commit()

        log_audit(
            db,
            "system_init",
            detail={"message": "Admin iniziale creato", "username": settings.ADMIN_USERNAME},
        )
