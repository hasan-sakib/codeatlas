import pytest
from fastapi.testclient import TestClient

from tests.integration.api.conftest import register_and_login

pytestmark = pytest.mark.integration


def _create_workspace(client: TestClient, headers: dict[str, str], name: str) -> str:
    resp = client.post("/api/v1/workspaces", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    workspace_id: str = resp.json()["id"]
    return workspace_id


def test_create_list_get_delete_repository_flow(api_client: TestClient) -> None:
    token = register_and_login(api_client, "amina.repo@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = _create_workspace(api_client, headers, "Repo Flow")

    create_resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        json={"git_url": "https://github.com/org/repo.git"},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    repository = create_resp.json()
    assert repository["workspace_id"] == workspace_id
    assert repository["status"] == "indexing"

    list_resp = api_client.get(f"/api/v1/workspaces/{workspace_id}/repositories", headers=headers)
    assert list_resp.status_code == 200
    assert [r["id"] for r in list_resp.json()] == [repository["id"]]

    get_resp = api_client.get(
        f"/api/v1/workspaces/{workspace_id}/repositories/{repository['id']}", headers=headers
    )
    assert get_resp.status_code == 200

    delete_resp = api_client.delete(
        f"/api/v1/workspaces/{workspace_id}/repositories/{repository['id']}", headers=headers
    )
    assert delete_resp.status_code == 204

    get_after_delete = api_client.get(
        f"/api/v1/workspaces/{workspace_id}/repositories/{repository['id']}", headers=headers
    )
    assert get_after_delete.status_code == 404


def test_create_repository_rejects_disallowed_url_scheme(api_client: TestClient) -> None:
    token = register_and_login(api_client, "badurl.repo@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = _create_workspace(api_client, headers, "Bad URL")

    resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        json={"git_url": "file:///etc/passwd"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_repository_is_isolated_to_its_workspace(api_client: TestClient) -> None:
    token = register_and_login(api_client, "tenant.repo@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    workspace_a = _create_workspace(api_client, headers, "Tenant A")
    workspace_b = _create_workspace(api_client, headers, "Tenant B")

    create_resp = api_client.post(
        f"/api/v1/workspaces/{workspace_a}/repositories",
        json={"git_url": "https://github.com/org/a.git"},
        headers=headers,
    )
    repository_id = create_resp.json()["id"]

    # Same owner, but the repository belongs to workspace_a, not
    # workspace_b — cross-workspace lookup must 404, not leak the row.
    cross_resp = api_client.get(
        f"/api/v1/workspaces/{workspace_b}/repositories/{repository_id}", headers=headers
    )
    assert cross_resp.status_code == 404


def test_indexing_job_status_is_pollable_and_repository_scoped(api_client: TestClient) -> None:
    token = register_and_login(api_client, "jobstatus.repo@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    workspace_a = _create_workspace(api_client, headers, "Job Status A")
    workspace_b = _create_workspace(api_client, headers, "Job Status B")

    create_resp = api_client.post(
        f"/api/v1/workspaces/{workspace_a}/repositories",
        json={"git_url": "https://github.com/org/jobstatus.git"},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    repository_id = create_resp.json()["id"]

    list_resp = api_client.get(
        f"/api/v1/workspaces/{workspace_a}/repositories/{repository_id}/jobs", headers=headers
    )
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    assert len(jobs) == 1
    job_id = jobs[0]["id"]
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["repository_id"] == repository_id

    get_resp = api_client.get(
        f"/api/v1/workspaces/{workspace_a}/repositories/{repository_id}/jobs/{job_id}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == job_id

    # Same job id, wrong workspace in the URL — must 404, not leak it.
    cross_resp = api_client.get(
        f"/api/v1/workspaces/{workspace_b}/repositories/{repository_id}/jobs/{job_id}",
        headers=headers,
    )
    assert cross_resp.status_code == 404


def test_repository_routes_require_workspace_ownership(api_client: TestClient) -> None:
    owner_token = register_and_login(api_client, "owner.repo@example.com")
    other_token = register_and_login(api_client, "other.repo@example.com")
    workspace_id = _create_workspace(
        api_client, {"Authorization": f"Bearer {owner_token}"}, "Owner Workspace"
    )

    resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/repositories",
        json={"git_url": "https://github.com/org/repo.git"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404
