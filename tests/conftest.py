"""Fixture globali per la test suite.

NB: l'ordine degli import è critico — le variabili d'ambiente vanno settate
PRIMA di importare `app.*`, perché `app.config.settings` viene istanziato a
import-time e `app.database.engine` dipende da `settings.DATABASE_URL`.
"""

import os
import tempfile

# Env setup — deve precedere qualunque `from app...`
os.environ["ADMIN_PASSWORD"] = "testadmin123"
_db_fd, _db_path = tempfile.mkstemp(suffix=".db", prefix="mubitools-test-")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    """TestClient con lifespan attivo (crea tabelle + admin)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client) -> dict[str, str]:
    """Header Authorization con token JWT admin valido."""
    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "testadmin123"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def pytest_sessionfinish(session, exitstatus):
    """Cleanup del DB temporaneo a fine sessione."""
    try:
        os.unlink(_db_path)
    except FileNotFoundError:
        pass
