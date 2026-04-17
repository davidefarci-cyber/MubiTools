"""Smoke test: pannello admin (auth richiesta)."""


def test_admin_users_requires_auth(client):
    response = client.get("/admin/users")
    assert response.status_code in (401, 403)


def test_admin_users_with_admin_token_returns_list(client, auth_headers):
    response = client.get("/admin/users", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    usernames = [u.get("username") for u in payload]
    assert "admin" in usernames
