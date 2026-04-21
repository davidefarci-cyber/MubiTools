"""Smoke test: health check pubblico."""


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload
    assert "uptime_seconds" in payload
    assert isinstance(payload["uptime_seconds"], int)
