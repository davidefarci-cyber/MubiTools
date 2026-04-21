"""Smoke test: modulo invio_remi — endpoint protetto."""


def test_invio_remi_settings_requires_auth(client):
    response = client.get("/api/invio-remi/settings")
    assert response.status_code in (401, 403)
