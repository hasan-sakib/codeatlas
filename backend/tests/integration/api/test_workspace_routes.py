import pytest
from fastapi.testclient import TestClient

from tests.integration.api.conftest import register_and_login

pytestmark = pytest.mark.integration


def test_create_list_and_get_workspace_flow(api_client: TestClient) -> None:
    token = register_and_login(api_client, "amina.workspace@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = api_client.post(
        "/api/v1/workspaces", json={"name": "My Project", "description": "desc"}, headers=headers
    )
    assert create_resp.status_code == 201, create_resp.text
    workspace = create_resp.json()
    assert workspace["slug"] == "my-project"
    assert workspace["description"] == "desc"

    list_resp = api_client.get("/api/v1/workspaces", headers=headers)
    assert list_resp.status_code == 200
    assert [w["id"] for w in list_resp.json()] == [workspace["id"]]

    get_resp = api_client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == workspace["id"]


def test_create_workspace_duplicate_name_returns_409(api_client: TestClient) -> None:
    token = register_and_login(api_client, "dup.workspace@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    first = api_client.post("/api/v1/workspaces", json={"name": "Same Name"}, headers=headers)
    assert first.status_code == 201

    second = api_client.post("/api/v1/workspaces", json={"name": "Same Name"}, headers=headers)
    assert second.status_code == 409


def test_workspace_routes_require_authentication(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/workspaces").status_code in (401, 403)
    assert api_client.post("/api/v1/workspaces", json={"name": "x"}).status_code in (401, 403)


def test_get_workspace_owned_by_another_user_returns_404(api_client: TestClient) -> None:
    owner_token = register_and_login(api_client, "owner.workspace@example.com")
    other_token = register_and_login(api_client, "other.workspace@example.com")

    create_resp = api_client.post(
        "/api/v1/workspaces",
        json={"name": "Owner Only"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    workspace_id = create_resp.json()["id"]

    resp = api_client.get(
        f"/api/v1/workspaces/{workspace_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404
