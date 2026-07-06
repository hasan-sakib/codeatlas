# Module 5: Authentication

## Token lifecycle

- **Access token**: JWT (HS256), 15 minute TTL, claims `sub` (user id), `jti` (random id used for blacklisting), `exp`. Signed/verified with `SecuritySettings.jwt_secret_key`.
- **Refresh token**: opaque `secrets.token_urlsafe(32)` string. Only its SHA-256 hash is ever persisted (`refresh_tokens.token_hash`); the plaintext is returned to the client once and never stored.
- **Rotation on use**: every successful `/auth/refresh` call revokes the presented token's row (`revoked_at = now()`) and inserts a brand-new refresh token row in the same operation. Presenting an already-revoked (or unknown, or expired) token raises `InvalidRefreshTokenError` → `401`.
- **Logout**: revokes the refresh token row and blacklists the access token's `jti` in Redis with a TTL equal to the token's *remaining* lifetime (`expires_at - now`), so the blacklist entry never outlives the token it's blocking and never needs manual cleanup.
- **Password hashing**: argon2 via `argon2-cffi` (`PasswordHasher().hash`/`.verify`), not bcrypt — chosen per `DESIGN.md` §23 to keep pace with future hardware.

```
register → login → [access + refresh pair]
                        │
        Authorization: Bearer <access> ──► require_current_user
                        │                     (decode JWT → check blacklist → load user → is_active)
                        │
        POST /auth/refresh {refresh} ──► rotate: revoke old row, issue new pair
                        │
        POST /auth/logout {refresh} ──► revoke refresh row + blacklist access jti
```

## Layering

- `app/domain/entities/user.py`, `value_objects/token_pair.py` — no framework deps.
- `app/domain/exceptions.py` — `InvalidCredentialsError`, `EmailAlreadyExistsError`, `InvalidRefreshTokenError`.
- `app/domain/ports/token_blacklist.py` — `TokenBlacklistPort` Protocol (`blacklist`, `is_blacklisted`).
- `app/core/security.py` — pure functions: `hash_password`/`verify_password`, `create_access_token`/`decode_access_token`, `generate_refresh_token`/`hash_refresh_token`. No DB or Redis access — this module only knows about cryptography and JWT encoding.
- `app/infrastructure/cache/redis_token_blacklist.py` — `RedisTokenBlacklistAdapter` (`SETEX`/`EXISTS`, `"auth:blacklist:"` key prefix).
- `app/application/use_cases/auth/` — `RegisterUserUseCase`, `LoginUseCase`, `RefreshTokenUseCase`, `LogoutUseCase`. `login.py` and `refresh_token.py` share an `issue_token_pair()` helper so both code paths that mint a fresh pair stay identical.
- `app/api/deps.py` — `require_current_user` (decode → blacklist check → load user → `is_active` check) and `require_workspace_access` (owner-only; returns `404` for both "workspace doesn't exist" and "not yours", deliberately, to avoid leaking which workspace IDs exist to non-owners).
- `app/api/routers/auth.py` — `/register` (201/409), `/login` (200/401), `/refresh` (200/401), `/logout` (204), `/me` (200).

## Real bugs found while building this (not just design-doc theory)

1. **Refresh token rotation had a TOCTOU race.** A naive "look up token → check not revoked → revoke it → insert new row" sequence lets two concurrent requests presenting the *same* refresh token both pass the "not revoked" check before either writes, minting two valid token pairs from one refresh token. Fixed by adding `RefreshTokenRepository.revoke_if_active(token_id) -> bool`, implemented as a single conditional `UPDATE refresh_tokens SET revoked_at = now() WHERE id = :id AND revoked_at IS NULL`, checking `rowcount`. Postgres's row-level lock on the `UPDATE` means only one concurrent caller can ever see `rowcount == 1`; the other sees `0` and raises `InvalidRefreshTokenError`. Verified empirically (not just argued) with a real two-`asyncio.gather()`-session integration test (`tests/integration/application/use_cases/auth/test_refresh_token_concurrency.py`) — asserts `sorted(results) == ["rejected", "success"]`. Passed on the first run once the fix was in place, and — checked by temporarily reverting to the naive lookup-then-revoke sequence — reliably failed (`["success", "success"]`) beforehand, confirming the test actually exercises the race rather than passing by luck.
2. **`redis>=5.2` ships its own inline types (`py.typed`), but the pre-commit `mypy` hook still flagged `redis.asyncio` as "Library stubs not installed."** The hook runs in its own isolated virtualenv containing only what's listed in `additional_dependencies` (previously just `pydantic`) — `redis` itself wasn't installed there, so mypy fell back to its bundled "known third-party stub packages" list and suggested the now-unnecessary `types-redis`. `uv run mypy app` (the project's own fully-populated venv) never showed this, which is why it surfaced only when `pre-commit run --all-files` was actually run for this module. Fixed by adding `redis>=5.2,<6` to the mypy hook's `additional_dependencies` in `.pre-commit-config.yaml`, matching the existing `pydantic` entry — real type checking of our Redis usage, not a suppressed/ignored import.

## Testing notes

- Unit tests use fakes (`tests/unit/application/use_cases/auth/fakes.py`: `FakeUserRepository`, `FakeRefreshTokenRepository` — implements `revoke_if_active` with the same atomicity contract as the real one — and `FakeTokenBlacklist`), never a real DB or Redis.
- `tests/unit/core/test_security.py` — password round-trip/salting, JWT roundtrip/tamper/wrong-secret/expiry rejection, refresh-token hash determinism.
- `tests/unit/api/test_deps.py` — `require_current_user` rejects blacklisted/expired/invalid tokens and inactive users; `require_workspace_access` returns 404 (not 403) for both a missing workspace and a non-owner.
- Integration tests (`tests/integration/`, real Postgres + Redis via `testcontainers`): full register → login → `/me` → refresh → reuse-rejected → logout → blacklisted-access-rejected → revoked-refresh-rejected flow through actual HTTP routes (`TestClient`), plus the concurrency race test described above.
- Live smoke test (manual, not part of CI): booted `create_app()` against throwaway `postgres:16`/`redis:7` containers and a real `alembic upgrade head`, then curled the full `/api/v1/auth/*` flow end-to-end — every status code (201, 200, 403 unauthenticated, 401 reused-refresh, 204 logout, 401 blacklisted-access) matched the design exactly.
- `pytest -q` (unit): 58 passed. `pytest -m integration`: 9 passed. `mypy app`: no issues, 81 source files. `ruff check` / `black --check`: clean. `pre-commit run --all-files`: clean (after the redis mypy-dependency fix above).
