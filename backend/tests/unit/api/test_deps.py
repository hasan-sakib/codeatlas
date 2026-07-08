from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import require_current_user, require_repository_access, require_workspace_access
from app.core.config import SecuritySettings
from app.core.security import create_access_token
from app.domain.entities.repository import Repository, RepositorySourceType, RepositoryStatus
from app.domain.entities.user import User
from app.domain.entities.workspace import Workspace
from app.domain.exceptions import RepositoryNotFoundError, WorkspaceNotFoundError
from tests.unit.application.use_cases.auth.fakes import FakeTokenBlacklist, FakeUserRepository


def _settings() -> SecuritySettings:
    return SecuritySettings(jwt_secret_key="a-sufficiently-long-test-secret-key-value")  # type: ignore[arg-type]


def _make_user(**overrides: object) -> User:
    now = datetime.now(UTC)
    defaults: dict[str, object] = dict(
        id=uuid4(),
        email="amina@example.com",
        hashed_password="irrelevant",
        full_name=None,
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return User(**defaults)  # type: ignore[arg-type]


async def test_require_current_user_rejects_blacklisted_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings", lambda: type("S", (), {"security": _settings()})()
    )
    settings = _settings()
    user = _make_user()
    user_repo = FakeUserRepository()
    await user_repo.add(user)
    token, jti = create_access_token(user.id, settings)
    blacklist = FakeTokenBlacklist()
    await blacklist.blacklist(jti, 900)

    with pytest.raises(HTTPException) as exc_info:
        await require_current_user(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            user_repo=user_repo,
            blacklist=blacklist,
        )

    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()


async def test_require_current_user_accepts_valid_non_blacklisted_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings", lambda: type("S", (), {"security": _settings()})()
    )
    settings = _settings()
    user = _make_user()
    user_repo = FakeUserRepository()
    await user_repo.add(user)
    token, _jti = create_access_token(user.id, settings)
    blacklist = FakeTokenBlacklist()

    result = await require_current_user(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        user_repo=user_repo,
        blacklist=blacklist,
    )

    assert result.id == user.id


async def test_require_current_user_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings", lambda: type("S", (), {"security": _settings()})()
    )
    user_repo = FakeUserRepository()
    blacklist = FakeTokenBlacklist()

    with pytest.raises(HTTPException) as exc_info:
        await require_current_user(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt"),
            user_repo=user_repo,
            blacklist=blacklist,
        )

    assert exc_info.value.status_code == 401


async def test_require_current_user_rejects_inactive_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings", lambda: type("S", (), {"security": _settings()})()
    )
    settings = _settings()
    user = _make_user(is_active=False)
    user_repo = FakeUserRepository()
    await user_repo.add(user)
    token, _jti = create_access_token(user.id, settings)
    blacklist = FakeTokenBlacklist()

    with pytest.raises(HTTPException) as exc_info:
        await require_current_user(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            user_repo=user_repo,
            blacklist=blacklist,
        )

    assert exc_info.value.status_code == 401


async def test_require_current_user_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings", lambda: type("S", (), {"security": _settings()})()
    )
    expired_settings = SecuritySettings(  # type: ignore[arg-type]
        jwt_secret_key="a-sufficiently-long-test-secret-key-value",
        access_token_expire_minutes=-1,
    )
    user = _make_user()
    user_repo = FakeUserRepository()
    await user_repo.add(user)
    token, _jti = create_access_token(user.id, expired_settings)
    blacklist = FakeTokenBlacklist()

    with pytest.raises(HTTPException) as exc_info:
        await require_current_user(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            user_repo=user_repo,
            blacklist=blacklist,
        )

    assert exc_info.value.status_code == 401


class _FakeWorkspaceRepository:
    def __init__(self, workspace: Workspace | None) -> None:
        self._workspace = workspace

    async def add(self, workspace: Workspace) -> Workspace:
        raise NotImplementedError

    async def get_by_id(self, workspace_id: object) -> Workspace | None:
        return self._workspace

    async def list_for_owner(self, owner_id: object) -> list[Workspace]:
        raise NotImplementedError

    async def delete(self, workspace_id: object) -> None:
        raise NotImplementedError


def _make_workspace(owner_id: object) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=uuid4(),
        owner_id=owner_id,  # type: ignore[arg-type]
        name="Test",
        slug="test",
        description=None,
        created_at=now,
        updated_at=now,
    )


async def test_require_workspace_access_allows_owner() -> None:
    owner = _make_user()
    workspace = _make_workspace(owner.id)
    repo = _FakeWorkspaceRepository(workspace)

    result = await require_workspace_access(
        workspace_id=workspace.id, user=owner, workspace_repo=repo
    )

    assert result is workspace


async def test_require_workspace_access_rejects_non_owner() -> None:
    # WorkspaceNotFoundError propagates to the global domain exception
    # handler (404) — see app/api/middleware/error_handling.py — rather
    # than being converted to HTTPException at this layer.
    owner = _make_user()
    other_user = _make_user(id=uuid4(), email="other@example.com")
    workspace = _make_workspace(owner.id)
    repo = _FakeWorkspaceRepository(workspace)

    with pytest.raises(WorkspaceNotFoundError):
        await require_workspace_access(
            workspace_id=workspace.id, user=other_user, workspace_repo=repo
        )


async def test_require_workspace_access_rejects_missing_workspace() -> None:
    user = _make_user()
    repo = _FakeWorkspaceRepository(None)

    with pytest.raises(WorkspaceNotFoundError):
        await require_workspace_access(workspace_id=uuid4(), user=user, workspace_repo=repo)


class _FakeRepositoryRepository:
    def __init__(self, repository: Repository | None) -> None:
        self._repository = repository

    async def add(self, repository: Repository) -> Repository:
        raise NotImplementedError

    async def get_by_id(self, repository_id: object) -> Repository | None:
        return self._repository

    async def list_by_workspace(self, workspace_id: object) -> list[Repository]:
        raise NotImplementedError

    async def update_status(self, repository_id: object, status: object, **kwargs: object) -> None:
        raise NotImplementedError

    async def delete(self, repository_id: object) -> None:
        raise NotImplementedError


def _make_repository(workspace_id: object) -> Repository:
    now = datetime.now(UTC)
    return Repository(
        id=uuid4(),
        workspace_id=workspace_id,  # type: ignore[arg-type]
        source_type=RepositorySourceType.GIT_URL,
        git_url="https://github.com/example/repo.git",
        default_branch="main",
        local_path=None,
        last_indexed_commit_sha=None,
        status=RepositoryStatus.READY,
        created_at=now,
        updated_at=now,
    )


async def test_require_repository_access_allows_repository_in_the_workspace() -> None:
    owner = _make_user()
    workspace = _make_workspace(owner.id)
    repository = _make_repository(workspace.id)
    repository_repo = _FakeRepositoryRepository(repository)

    result = await require_repository_access(
        repository_id=repository.id, workspace=workspace, repository_repo=repository_repo
    )

    assert result is repository


async def test_require_repository_access_rejects_missing_repository() -> None:
    workspace = _make_workspace(uuid4())
    repository_repo = _FakeRepositoryRepository(None)

    with pytest.raises(RepositoryNotFoundError):
        await require_repository_access(
            repository_id=uuid4(), workspace=workspace, repository_repo=repository_repo
        )


async def test_require_repository_access_rejects_repository_in_a_different_workspace() -> None:
    workspace = _make_workspace(uuid4())
    repository = _make_repository(uuid4())  # belongs to a different workspace
    repository_repo = _FakeRepositoryRepository(repository)

    with pytest.raises(RepositoryNotFoundError):
        await require_repository_access(
            repository_id=repository.id, workspace=workspace, repository_repo=repository_repo
        )
