"""Costanti condivise tra moduli.

Aggiungere qui magic value ricorrenti (non business-specific).
"""

# Parametri SMTP Aruba — usati da invio_remi/email_service e admin/pec_service
SMTP_HOST = "smtps.pec.aruba.it"
SMTP_PORT = 465
SMTP_SEND_TIMEOUT = 30   # timeout per invio PEC reale
SMTP_TEST_TIMEOUT = 10   # timeout per test login (admin)
