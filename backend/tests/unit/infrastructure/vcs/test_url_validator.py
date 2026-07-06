import socket

import pytest

from app.infrastructure.vcs.url_validator import (
    RepositoryUrlValidationError,
    resolve_and_check_ip,
    validate_repository_url,
)


def test_validate_repository_url_accepts_https() -> None:
    validate_repository_url("https://github.com/org/repo.git")


def test_validate_repository_url_accepts_ssh_with_git_user() -> None:
    validate_repository_url("ssh://git@github.com/org/repo.git")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/repo.git",
        "git://example.com/repo.git",
    ],
)
def test_validate_repository_url_rejects_disallowed_scheme(url: str) -> None:
    with pytest.raises(RepositoryUrlValidationError):
        validate_repository_url(url)


def test_validate_repository_url_rejects_missing_hostname() -> None:
    with pytest.raises(RepositoryUrlValidationError):
        validate_repository_url("https:///org/repo.git")


def test_validate_repository_url_rejects_embedded_password() -> None:
    with pytest.raises(RepositoryUrlValidationError):
        validate_repository_url("https://user:pass@github.com/org/repo.git")


def test_validate_repository_url_rejects_embedded_username_for_https() -> None:
    with pytest.raises(RepositoryUrlValidationError):
        validate_repository_url("https://user@github.com/org/repo.git")


def test_validate_repository_url_rejects_unexpected_port() -> None:
    with pytest.raises(RepositoryUrlValidationError):
        validate_repository_url("https://github.com:6379/org/repo.git")


def test_validate_repository_url_accepts_explicit_default_port() -> None:
    validate_repository_url("https://github.com:443/org/repo.git")


async def test_resolve_and_check_ip_rejects_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(RepositoryUrlValidationError):
        await resolve_and_check_ip("localhost")


async def test_resolve_and_check_ip_rejects_private_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(RepositoryUrlValidationError):
        await resolve_and_check_ip("internal.example.com")


async def test_resolve_and_check_ip_rejects_cloud_metadata_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(host: str, port: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(RepositoryUrlValidationError):
        await resolve_and_check_ip("metadata.internal")


async def test_resolve_and_check_ip_rejects_ipv6_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0, 0, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(RepositoryUrlValidationError):
        await resolve_and_check_ip("localhost6")


async def test_resolve_and_check_ip_accepts_public_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("140.82.121.3", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    await resolve_and_check_ip("github.com")  # must not raise


async def test_resolve_and_check_ip_wraps_dns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: object) -> list[tuple[object, ...]]:
        raise socket.gaierror("not found")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(RepositoryUrlValidationError):
        await resolve_and_check_ip("nonexistent.invalid")
