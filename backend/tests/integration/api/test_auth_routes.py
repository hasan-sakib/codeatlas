import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_full_register_login_refresh_logout_flow(api_client: TestClient) -> None:
    email = "amina.flow@example.com"
    password = "correct-horse-battery-staple"

    register_resp = api_client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert register_resp.status_code == 201, register_resp.text
    user_id = register_resp.json()["id"]

    unauthenticated_resp = api_client.get("/api/v1/auth/me")
    assert unauthenticated_resp.status_code in (401, 403)

    login_resp = api_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200, login_resp.text
    tokens = login_resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    me_resp = api_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_resp.status_code == 200, me_resp.text
    assert me_resp.json()["id"] == user_id

    refresh_resp = api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200, refresh_resp.text
    new_tokens = refresh_resp.json()
    new_access_token = new_tokens["access_token"]
    new_refresh_token = new_tokens["refresh_token"]
    assert new_refresh_token != refresh_token

    # the old (now-rotated) refresh token must be rejected on reuse
    reuse_resp = api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401, reuse_resp.text

    logout_resp = api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_refresh_token},
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert logout_resp.status_code == 204, logout_resp.text

    # the just-blacklisted access token must be rejected immediately
    blacklisted_resp = api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access_token}"}
    )
    assert blacklisted_resp.status_code == 401, blacklisted_resp.text

    # the revoked-at-logout refresh token must also be rejected
    revoked_resp = api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_refresh_token}
    )
    assert revoked_resp.status_code == 401, revoked_resp.text


def test_duplicate_registration_returns_409(api_client: TestClient) -> None:
    email = "dup.flow@example.com"
    first = api_client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    assert first.status_code == 201

    second = api_client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password456"}
    )
    assert second.status_code == 409


def test_login_with_wrong_password_returns_401(api_client: TestClient) -> None:
    email = "wrongpass.flow@example.com"
    api_client.post("/api/v1/auth/register", json={"email": email, "password": "correct-password"})

    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )

    assert resp.status_code == 401


def test_login_is_rate_limited_per_ip(api_client: TestClient) -> None:
    # Default RATE_LIMIT__AUTH_PER_IP_PER_MINUTE is 5 — the 6th attempt
    # within the window must be rejected regardless of credentials,
    # confirming the dependency is actually wired onto this route (not
    # just unit-tested in isolation, see test_rate_limit.py).
    email = "ratelimited.flow@example.com"
    api_client.post("/api/v1/auth/register", json={"email": email, "password": "correct-password"})

    for _ in range(5):
        resp = api_client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert resp.status_code == 401

    sixth = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )
    assert sixth.status_code == 429
    assert "Retry-After" in sixth.headers
