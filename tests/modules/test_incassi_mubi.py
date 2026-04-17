"""Smoke test: modulo incassi_mubi — endpoint protetto."""


def test_incassi_status_requires_auth(client):
    response = client.get("/api/incassi/status")
    assert response.status_code in (401, 403)
