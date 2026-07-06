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
