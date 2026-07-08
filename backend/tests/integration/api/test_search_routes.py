import pytest
from fastapi.testclient import TestClient

from tests.integration.api.conftest import register_and_login

pytestmark = pytest.mark.integration


def test_search_requires_authentication(api_client: TestClient) -> None:
    resp = api_client.post(
        f"/api/v1/workspaces/{__import__('uuid').uuid4()}/search", json={"query": "foo"}
    )
    assert resp.status_code in (401, 403)


def test_search_requires_workspace_ownership(api_client: TestClient) -> None:
    owner_token = register_and_login(api_client, "owner.search@example.com")
    other_token = register_and_login(api_client, "other.search@example.com")

    create_resp = api_client.post(
        "/api/v1/workspaces",
        json={"name": "Search Owner Only"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    workspace_id = create_resp.json()["id"]

    resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/search",
        json={"query": "foo"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_search_rejects_invalid_limit(api_client: TestClient) -> None:
    token = register_and_login(api_client, "invalid.search@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = api_client.post(
        "/api/v1/workspaces", json={"name": "Invalid Limit"}, headers=headers
    ).json()["id"]

    resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/search",
        json={"query": "foo", "limit": 0},
        headers=headers,
    )
    assert resp.status_code == 422
