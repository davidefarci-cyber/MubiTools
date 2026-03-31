"""Rate limiting per endpoint di login.

Limita a MAX_ATTEMPTS tentativi per minuto per IP.
Implementazione in-memory (adatta per singola istanza).
"""

import time
from collections import defaultdict
from threading import Lock

MAX_ATTEMPTS: int = 5
WINDOW_SECONDS: int = 60

_attempts: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def check_rate_limit(client_ip: str) -> None:
    """Verifica che l'IP non abbia superato il limite di tentativi.

    Raises:
        RateLimitExceeded: Se l'IP ha superato MAX_ATTEMPTS nell'ultimo minuto.
    """
    now = time.time()
    cutoff = now - WINDOW_SECONDS

    with _lock:
        # Rimuovi tentativi scaduti
        _attempts[client_ip] = [t for t in _attempts[client_ip] if t > cutoff]

        if len(_attempts[client_ip]) >= MAX_ATTEMPTS:
            raise RateLimitExceeded()

        _attempts[client_ip].append(now)


class RateLimitExceeded(Exception):
    """Eccezione per rate limit superato."""

    pass
