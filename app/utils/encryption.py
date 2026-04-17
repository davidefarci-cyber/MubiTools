"""Cifratura password PEC con Fernet (symmetric encryption)."""

from cryptography.fernet import Fernet

from app.config import BASE_DIR

_KEY_PATH = BASE_DIR / "data" / "secret.key"

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Restituisce l'istanza Fernet, generando la chiave se necessario."""
    global _fernet
    if _fernet is not None:
        return _fernet

    if _KEY_PATH.exists():
        key = _KEY_PATH.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _KEY_PATH.write_bytes(key)

    _fernet = Fernet(key)
    return _fernet


def encrypt_password(plain: str) -> str:
    """Cifra una password in chiaro e restituisce il token Fernet come stringa."""
    f = _get_fernet()
    return f.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_password(encrypted: str) -> str:
    """Decifra un token Fernet e restituisce la password in chiaro."""
    f = _get_fernet()
    return f.decrypt(encrypted.encode("utf-8")).decode("utf-8")


# Genera la chiave al primo import se non esiste
_get_fernet()
