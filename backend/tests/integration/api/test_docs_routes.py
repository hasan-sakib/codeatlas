import pytest
from fastapi.testclient import TestClient

from tests.integration.api.conftest import register_and_login

pytestmark = pytest.mark.integration


def test_generate_docs_requires_authentication(api_client: TestClient) -> None:
    resp = api_client.post(
        f"/api/v1/workspaces/{__import__('uuid').uuid4()}"
        f"/repositories/{__import__('uuid').uuid4()}/docs/generate",
        json={"scope": "repository"},
    )
    assert resp.status_code in (401, 403)


def test_generate_docs_requires_repository_ownership(api_client: TestClient) -> None:
    owner_token = register_and_login(api_client, "owner.docs@example.com")
    other_token = register_and_login(api_client, "other.docs@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    workspace_id = api_client.post(
        "/api/v1/workspaces", json={"name": "Docs Owner Only"}, headers=owner_headers
    ).json()["id"]
    repository_id = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        json={"git_url": "https://github.com/octocat/Hello-World.git"},
        headers=owner_headers,
    ).json()["id"]

    resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories/{repository_id}/docs/generate",
        json={"scope": "repository"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_generate_docs_requires_path_for_non_repository_scope(api_client: TestClient) -> None:
    token = register_and_login(api_client, "path.docs@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = api_client.post(
        "/api/v1/workspaces", json={"name": "Docs Path Required"}, headers=headers
    ).json()["id"]
    repository_id = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        json={"git_url": "https://github.com/octocat/Hello-World.git"},
        headers=headers,
    ).json()["id"]

    resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories/{repository_id}/docs/generate",
        json={"scope": "file"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_generate_docs_rejects_missing_repository(api_client: TestClient) -> None:
    token = register_and_login(api_client, "missing-repo.docs@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = api_client.post(
        "/api/v1/workspaces", json={"name": "Docs Missing Repo"}, headers=headers
    ).json()["id"]

    resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories/{__import__('uuid').uuid4()}"
        "/docs/generate",
        json={"scope": "repository"},
        headers=headers,
    )
    assert resp.status_code == 404
