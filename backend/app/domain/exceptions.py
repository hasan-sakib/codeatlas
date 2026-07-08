from uuid import UUID


class DomainError(Exception):
    """Base class for all domain-level exceptions."""


class InvalidCredentialsError(DomainError):
    """Wrong email or password. Deliberately generic — never reveal
    whether the email exists (avoids user-enumeration)."""


class EmailAlreadyExistsError(DomainError):
    def __init__(self, email: str) -> None:
        super().__init__(f"Email already registered: {email}")
        self.email = email


class InvalidRefreshTokenError(DomainError):
    """Refresh token not found, expired, or already rotated/revoked."""


class WorkspaceNotFoundError(DomainError):
    """Workspace doesn't exist, or exists but isn't owned by the requester.

    Deliberately one exception for both cases (see require_workspace_access
    in api/deps.py) — never reveal whether a workspace ID exists to a
    non-owner.
    """


class WorkspaceSlugAlreadyExistsError(DomainError):
    def __init__(self, owner_id: UUID, slug: str) -> None:
        super().__init__(f"Workspace slug already exists for owner {owner_id}: {slug}")
        self.slug = slug


class RepositoryNotFoundError(DomainError):
    """Repository doesn't exist, or exists but isn't in the given workspace.

    Same anti-enumeration rationale as WorkspaceNotFoundError.
    """


class RepositoryAlreadyIndexingError(DomainError):
    """A re-index was requested/implied while a job is already in flight."""


class LLMUnavailableError(DomainError):
    """The LLM backend (Ollama) could not be reached or errored after
    exhausting the configured retry budget."""


class ConversationNotFoundError(DomainError):
    """Conversation doesn't exist, or exists but is soft-deleted."""

    def __init__(self, conversation_id: UUID) -> None:
        super().__init__(f"Conversation not found: {conversation_id}")
        self.conversation_id = conversation_id
