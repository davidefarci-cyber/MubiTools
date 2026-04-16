"""Servizio di invio PEC con allegato PDF via SMTP Aruba."""

import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.models import PecAccount
from app.utils.encryption import decrypt_password

logger = logging.getLogger(__name__)

# Parametri SMTP Aruba fissi
SMTP_HOST = "smtps.pec.aruba.it"
SMTP_PORT = 465
SMTP_TIMEOUT = 30


async def send_pec(
    pec_account_id: int,
    to_address: str,
    subject: str,
    body: str,
    attachment: bytes,
    attachment_filename: str,
    *,
    db: Session,
) -> dict:
    """Invia una PEC con allegato PDF tramite SMTP Aruba.

    Args:
        pec_account_id: ID dell'account PEC da usare.
        to_address: Indirizzo email destinatario.
        subject: Oggetto dell'email.
        body: Corpo dell'email (testo semplice).
        attachment: Contenuto binario del PDF da allegare.
        attachment_filename: Nome del file allegato.
        db: Sessione database per recuperare l'account PEC.

    Returns:
        {"success": True} oppure {"success": False, "error": "messaggio errore"}
    """
    pec = db.query(PecAccount).filter(PecAccount.id == pec_account_id).first()
    if not pec:
        return {"success": False, "error": f"Account PEC id={pec_account_id} non trovato"}
    if not pec.is_active:
        return {"success": False, "error": f"Account PEC '{pec.label}' non attivo"}

    try:
        password = decrypt_password(pec.encrypted_password)
    except Exception as exc:
        logger.exception("Errore decifratura password PEC id=%d", pec_account_id)
        return {"success": False, "error": f"Errore decifratura password: {exc}"}

    # Componi il messaggio MIME
    msg = MIMEMultipart()
    msg["From"] = pec.email
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Allega il PDF
    file_part = MIMEBase("application", "pdf")
    file_part.set_payload(attachment)
    encoders.encode_base64(file_part)
    file_part.add_header(
        "Content-Disposition",
        f'attachment; filename="{attachment_filename}"',
    )
    msg.attach(file_part)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
            smtp.login(pec.username, password)
            smtp.sendmail(pec.email, [to_address], msg.as_string())
        logger.info("PEC inviata: from=%s to=%s subject=%s", pec.email, to_address, subject)
        return {"success": True}
    except smtplib.SMTPException as exc:
        logger.warning("Errore SMTP invio PEC: %s", exc)
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("Errore invio PEC")
        return {"success": False, "error": str(exc)}
