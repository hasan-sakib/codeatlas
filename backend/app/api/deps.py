from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.use_cases.workspaces.get_workspace import GetWorkspaceUseCase
from app.core.config import get_settings
from app.core.di import (
    provide_token_blacklist,
    provide_user_repository,
    provide_workspace_repository,
)
from app.core.security import decode_access_token
from app.domain.entities.user import User
from app.domain.entities.workspace import Workspace
from app.domain.exceptions import WorkspaceNotFoundError
from app.domain.ports.token_blacklist import TokenBlacklistPort
from app.domain.ports.user_repository import UserRepository
from app.domain.ports.workspace_repository import WorkspaceRepository

bearer_scheme = HTTPBearer(auto_error=True)


async def require_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    user_repo: Annotated[UserRepository, Depends(provide_user_repository)],
    blacklist: Annotated[TokenBlacklistPort, Depends(provide_token_blacklist)],
) -> User:
    settings = get_settings().security
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    # Checked *after* signature/expiry validation, since blacklist lookups
    # cost a Redis round-trip — no point paying it for an already-invalid
    # token. But blacklist status still takes precedence over anything
    # else once we get here: a logged-out token must not work again even
    # if its signature and expiry are otherwise fine.
    if await blacklist.is_blacklisted(claims.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    user = await user_repo.get_by_id(claims.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def require_workspace_access(
    workspace_id: UUID,
    user: Annotated[User, Depends(require_current_user)],
    workspace_repo: Annotated[WorkspaceRepository, Depends(provide_workspace_repository)],
) -> Workspace:
    """v1 is owner-only (see DESIGN.md §17) — a workspace_members table for
    team RBAC is future work. Returns 404 (not 403) whether the workspace
    doesn't exist or simply isn't the caller's, so an authenticated user
    can't distinguish "not found" from "not yours" (avoids leaking which
    workspace IDs exist). The actual check lives in GetWorkspaceUseCase —
    this is a thin FastAPI-specific translation of its exception."""
    try:
        return await GetWorkspaceUseCase(workspace_repo).execute(workspace_id, user.id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        ) from exc
