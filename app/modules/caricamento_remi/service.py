"""Servizi per il modulo Caricamento REMI."""


def validate_partita_iva(piva: str) -> bool:
    """Valida una Partita IVA italiana con algoritmo di checksum.

    Regole:
    - Esattamente 11 cifre numeriche
    - L'ultima cifra è il carattere di controllo calcolato con l'algoritmo standard

    Returns:
        True se la P.IVA è valida, False altrimenti.
    """
    if not piva or len(piva) != 11 or not piva.isdigit():
        return False

    digits = [int(c) for c in piva]

    # Somma cifre in posizione dispari (indice 0, 2, 4, 6, 8) — 1-indexed: 1, 3, 5, 7, 9
    odd_sum = sum(digits[i] for i in range(0, 10, 2))

    # Somma cifre in posizione pari (indice 1, 3, 5, 7, 9) — 1-indexed: 2, 4, 6, 8, 10
    even_sum = 0
    for i in range(1, 10, 2):
        doubled = digits[i] * 2
        even_sum += (doubled // 10) + (doubled % 10)

    total = odd_sum + even_sum
    check_digit = (10 - (total % 10)) % 10

    return check_digit == digits[10]
