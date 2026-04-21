"""Smoke test: modulo caricamento_remi — endpoint protetto."""


def test_caricamento_remi_stats_requires_auth(client):
    response = client.get("/api/caricamento-remi/history/stats")
    assert response.status_code in (401, 403)
