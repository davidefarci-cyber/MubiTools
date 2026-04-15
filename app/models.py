"""Modelli ORM per il database MUBI Tools."""

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.database import Base


class User(Base):
    """Modello utente con ruoli e moduli abilitati."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_modules: Mapped[str] = mapped_column(Text, default='["incassi_mubi","connessione"]')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")

    def get_modules(self) -> list[str]:
        """Restituisce la lista dei moduli abilitati."""
        if self.allowed_modules:
            return json.loads(self.allowed_modules)
        return []

    def set_modules(self, modules: list[str]) -> None:
        """Imposta la lista dei moduli abilitati."""
        self.allowed_modules = json.dumps(modules)

    def has_module(self, module_name: str) -> bool:
        """Verifica se l'utente ha accesso a un modulo."""
        return module_name in self.get_modules()


class AuditLog(Base):
    """Log di audit per tracciare ogni operazione significativa."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_timestamp", "timestamp"),
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User | None] = relationship(back_populates="audit_logs")


class PecAccount(Base):
    """Account PEC configurati (solo admin)."""

    __tablename__ = "pec_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DlRegistry(Base):
    """Anagrafica distributori locali."""

    __tablename__ = "dl_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    vat_number: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    pec_address: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RemiPractice(Base):
    """Storico pratiche REMI."""

    __tablename__ = "remi_practices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vat_number: Mapped[str] = mapped_column(Text, nullable=False)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    pec_address: Mapped[str] = mapped_column(Text, nullable=False)
    remi_code: Mapped[str] = mapped_column(Text, nullable=False)
    effective_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    batch_id: Mapped[str] = mapped_column(Text, nullable=False)
    send_batch_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def log_audit(
    db: Session,
    action: str,
    *,
    user_id: int | None = None,
    detail: dict | str | None = None,
) -> AuditLog:
    """Registra un'azione nell'audit log.

    Args:
        db: Sessione database.
        action: Tipo azione (es. 'incassi_upload', 'user_created').
        user_id: ID utente che ha eseguito l'azione (opzionale per azioni di sistema).
        detail: Dettagli aggiuntivi (dict serializzato in JSON, o stringa).
    """
    if isinstance(detail, dict):
        detail = json.dumps(detail, ensure_ascii=False)
    entry = AuditLog(
        user_id=user_id,
        action=action,
        detail=detail,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
