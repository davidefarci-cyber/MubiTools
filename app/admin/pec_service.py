"""Servizi admin: gestione account PEC (CRUD + test SMTP).

Errori di dominio sollevati come `ValueError` (dup email, ultima PEC attiva);
il router li mappa a `HTTPException`.
"""

import logging
import smtplib

from sqlalchemy.orm import Session

from app.models import PecAccount, log_audit
from app.shared.constants import SMTP_HOST, SMTP_PORT, SMTP_TEST_TIMEOUT
from app.utils.encryption import decrypt_password, encrypt_password

logger = logging.getLogger(__name__)


def list_pec_accounts(db: Session) -> list[PecAccount]:
    """Restituisce tutte le PEC ordinate per id."""
    return db.query(PecAccount).order_by(PecAccount.id).all()


def get_pec_by_id(db: Session, pec_id: int) -> PecAccount | None:
    """Trova una PEC per id."""
    return db.query(PecAccount).filter(PecAccount.id == pec_id).first()


def create_pec(
    db: Session,
    *,
    label: str,
    email: str,
    username: str,
    password: str,
    created_by_id: int | None = None,
) -> PecAccount:
    """Crea una nuova connessione PEC.

    Solleva `ValueError` se l'email è già configurata.
    """
    existing = db.query(PecAccount).filter(PecAccount.email == email).first()
    if existing:
        raise ValueError(f"Email PEC '{email}' gia' configurata")

    pec = PecAccount(
        label=label,
        email=email,
        username=username,
        encrypted_password=encrypt_password(password),
        is_active=True,
    )
    db.add(pec)
    db.commit()
    db.refresh(pec)

    log_audit(
        db, "pec_created",
        user_id=created_by_id,
        detail={"email": pec.email, "label": pec.label},
    )
    return pec


def update_pec(
    db: Session,
    *,
    pec: PecAccount,
    label: str | None = None,
    email: str | None = None,
    username: str | None = None,
    password: str | None = None,
    is_active: bool | None = None,
    updated_by_id: int | None = None,
) -> PecAccount:
    """Aggiorna i campi di una PEC esistente.

    Password: aggiornata solo se non vuota dopo strip().
    Solleva `ValueError` se la nuova email collide con un altro record.
    """
    if label is not None:
        pec.label = label

    if email is not None:
        dup = (
            db.query(PecAccount)
            .filter(PecAccount.email == email, PecAccount.id != pec.id)
            .first()
        )
        if dup:
            raise ValueError(f"Email PEC '{email}' gia' in uso")
        pec.email = email

    if username is not None:
        pec.username = username

    if password and password.strip():
        pec.encrypted_password = encrypt_password(password)

    if is_active is not None:
        pec.is_active = is_active

    db.commit()
    db.refresh(pec)

    log_audit(
        db, "pec_updated",
        user_id=updated_by_id,
        detail={"pec_id": pec.id, "email": pec.email},
    )
    return pec


def delete_pec(
    db: Session,
    *,
    pec: PecAccount,
    deleted_by_id: int | None = None,
) -> None:
    """Elimina una PEC.

    Solleva `ValueError` se è l'unica connessione PEC attiva.
    """
    active_count = (
        db.query(PecAccount).filter(PecAccount.is_active.is_(True)).count()
    )
    if pec.is_active and active_count <= 1:
        raise ValueError("Impossibile eliminare l'unica connessione PEC attiva")

    pec_id = pec.id
    email = pec.email
    db.delete(pec)
    db.commit()

    log_audit(
        db, "pec_deleted",
        user_id=deleted_by_id,
        detail={"pec_id": pec_id, "email": email},
    )


def test_pec_smtp(pec: PecAccount) -> tuple[bool, str | None]:
    """Verifica le credenziali PEC eseguendo solo il login SMTP_SSL.

    Pure: nessun side effect su DB, nessun audit. Il router decide come loggare l'esito.

    Returns:
        (True, None) su successo, (False, error_msg) su fallimento.
    """
    try:
        password = decrypt_password(pec.encrypted_password)
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TEST_TIMEOUT) as smtp:
            smtp.login(pec.username, password)
        return True, None
    except smtplib.SMTPException as exc:
        return False, str(exc)
    except Exception as exc:
        logger.exception("Errore test PEC id=%d", pec.id)
        return False, str(exc)
