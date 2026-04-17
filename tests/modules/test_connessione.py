"""Smoke test: modulo connessione — endpoint protetto."""


def test_connessione_status_requires_auth(client):
    response = client.get("/api/connessione/status")
    assert response.status_code in (401, 403)
