"""Smoke test: autenticazione JWT."""


def test_login_wrong_credentials_returns_401(client):
    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_login_admin_returns_token(client):
    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "testadmin123"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["username"] == "admin"
    assert payload["role"] == "admin"


def test_first_boot_is_public(client):
    response = client.get("/auth/first-boot")
    assert response.status_code == 200
    payload = response.json()
    assert "is_first_boot" in payload
    assert "has_backups" in payload
