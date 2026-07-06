from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import bearer_scheme, require_current_user
from app.api.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from app.application.use_cases.auth.login import LoginUseCase
from app.application.use_cases.auth.logout import LogoutUseCase
from app.application.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.application.use_cases.auth.register_user import RegisterUserUseCase
from app.core.config import get_settings
from app.core.di import (
    provide_refresh_token_repository,
    provide_token_blacklist,
    provide_user_repository,
)
from app.core.security import decode_access_token
from app.domain.entities.user import User
from app.domain.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.domain.ports.refresh_token_repository import RefreshTokenRepository
from app.domain.ports.token_blacklist import TokenBlacklistPort
from app.domain.ports.user_repository import UserRepository

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(require_current_user)]) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    user_repo: Annotated[UserRepository, Depends(provide_user_repository)],
) -> UserResponse:
    use_case = RegisterUserUseCase(user_repo)
    try:
        user = await use_case.execute(body.email, body.password, body.full_name)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name)


@router.post("/login", response_model=TokenPairResponse)
async def login(
    body: LoginRequest,
    user_repo: Annotated[UserRepository, Depends(provide_user_repository)],
    refresh_token_repo: Annotated[
        RefreshTokenRepository, Depends(provide_refresh_token_repository)
    ],
) -> TokenPairResponse:
    use_case = LoginUseCase(user_repo, refresh_token_repo, get_settings().security)
    try:
        tokens = await use_case.execute(body.email, body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from exc
    return TokenPairResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    body: RefreshRequest,
    refresh_token_repo: Annotated[
        RefreshTokenRepository, Depends(provide_refresh_token_repository)
    ],
) -> TokenPairResponse:
    use_case = RefreshTokenUseCase(refresh_token_repo, get_settings().security)
    try:
        tokens = await use_case.execute(body.refresh_token)
    except InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc
    return TokenPairResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    refresh_token_repo: Annotated[
        RefreshTokenRepository, Depends(provide_refresh_token_repository)
    ],
    blacklist: Annotated[TokenBlacklistPort, Depends(provide_token_blacklist)],
) -> None:
    settings = get_settings().security
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    use_case = LogoutUseCase(refresh_token_repo, blacklist)
    await use_case.execute(
        refresh_token=body.refresh_token,
        access_token_jti=claims.jti,
        access_token_expires_at=claims.expires_at,
    )
