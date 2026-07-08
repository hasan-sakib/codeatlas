import os

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.integration.api.conftest import register_and_login

pytestmark = pytest.mark.integration


def _real_ollama_is_reachable() -> bool:
    """CI has never provisioned a real Ollama (no service container, no
    model pull step) — only Postgres/Redis/Qdrant run via testcontainers.
    The one test below deliberately exercises the real LLM rather than a
    fake (see its own comment), so it needs a live Ollama to mean
    anything; skipping when none is reachable turns an environment gap
    into an honest "skipped" instead of a confusing assertion failure,
    while still running for real wherever one is available (e.g. local
    dev with `ollama serve`)."""
    base_url = os.environ.get("OLLAMA__BASE_URL", "http://localhost:11434")
    try:
        httpx.get(base_url, timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


requires_real_ollama = pytest.mark.skipif(
    not _real_ollama_is_reachable(),
    reason="No real Ollama instance reachable at OLLAMA__BASE_URL — this test intentionally "
    "exercises the real LLM end to end rather than a fake.",
)


def _create_workspace(client: TestClient, headers: dict[str, str], name: str) -> str:
    resp = client.post("/api/v1/workspaces", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    workspace_id: str = resp.json()["id"]
    return workspace_id


def test_create_list_get_delete_conversation_flow(api_client: TestClient) -> None:
    token = register_and_login(api_client, "amina.conversations@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = _create_workspace(api_client, headers, "Conv Workspace")

    create_resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations",
        json={"title": "My chat"},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    conversation = create_resp.json()
    assert conversation["title"] == "My chat"
    assert conversation["turn_count"] == 0

    list_resp = api_client.get(f"/api/v1/workspaces/{workspace_id}/conversations", headers=headers)
    assert list_resp.status_code == 200
    assert [c["id"] for c in list_resp.json()["data"]] == [conversation["id"]]

    get_resp = api_client.get(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation['id']}", headers=headers
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == conversation["id"]

    delete_resp = api_client.delete(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation['id']}", headers=headers
    )
    assert delete_resp.status_code == 204

    get_after_delete = api_client.get(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation['id']}", headers=headers
    )
    assert get_after_delete.status_code == 404


def test_conversation_routes_require_workspace_ownership(api_client: TestClient) -> None:
    owner_token = register_and_login(api_client, "owner.conversations@example.com")
    other_token = register_and_login(api_client, "other.conversations@example.com")
    workspace_id = _create_workspace(
        api_client, {"Authorization": f"Bearer {owner_token}"}, "Owner Only"
    )

    resp = api_client.get(
        f"/api/v1/workspaces/{workspace_id}/conversations",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


@requires_real_ollama
def test_send_message_streams_sse_response_and_persists_both_turns(
    api_client: TestClient,
) -> None:
    token = register_and_login(api_client, "chat.conversations@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = _create_workspace(api_client, headers, "Chat Workspace")

    create_resp = api_client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations", json={}, headers=headers
    )
    conversation_id = create_resp.json()["id"]

    # A casual greeting reliably classifies as GENERAL_CHAT (Module 13),
    # which skips retrieval entirely — keeps this test independent of a
    # real Qdrant/embedding pipeline while still exercising the real
    # agent graph, real Ollama, and real SSE streaming end to end.
    with api_client.stream(
        "POST",
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
        json={"content": "hey, thanks for your help!"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        lines = [line for line in response.iter_lines() if line]

    event_names = [line.removeprefix("event: ") for line in lines if line.startswith("event:")]
    assert "token" in event_names
    assert event_names[-1] == "done"

    messages_resp = api_client.get(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
        headers=headers,
    )
    assert messages_resp.status_code == 200
    messages = messages_resp.json()["data"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "hey, thanks for your help!"
    assert messages[1]["content"]  # real, non-empty generated text
