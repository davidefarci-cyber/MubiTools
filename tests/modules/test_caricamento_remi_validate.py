"""Unit test puro su validate_partita_iva (nessun I/O)."""

from app.modules.caricamento_remi.service import validate_partita_iva


def test_valid_piva():
    # Checksum verificato a mano: 12345678903 è una P.IVA valida
    assert validate_partita_iva("12345678903") is True


def test_invalid_checksum():
    assert validate_partita_iva("12345678901") is False


def test_non_numeric_piva():
    assert validate_partita_iva("abcdefghijk") is False


def test_empty_piva():
    assert validate_partita_iva("") is False


def test_wrong_length_piva():
    assert validate_partita_iva("123") is False
    assert validate_partita_iva("123456789012") is False
