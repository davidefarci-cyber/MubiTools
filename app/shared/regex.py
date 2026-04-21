"""Regex e validatori condivisi tra moduli."""

import re

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(address: str) -> bool:
    """Verifica che ``address`` rispetti il formato email/PEC accettato."""
    return bool(EMAIL_REGEX.match(address or ""))
