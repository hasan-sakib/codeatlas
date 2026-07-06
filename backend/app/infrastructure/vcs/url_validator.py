import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

# Conventional port per scheme. A repository URL asking for anything else
# (e.g. https://internal-host:6379) is a classic port-scanning/SSRF probe
# against internal services — reject it outright rather than "allowlist."
_ALLOWED_SCHEME_PORTS = {"https": 443, "ssh": 22}


class RepositoryUrlValidationError(Exception):
    """A repository URL failed scheme/format validation or resolves to a
    disallowed (private/loopback/link-local/reserved) address."""


def validate_repository_url(
    url: str, *, allowed_schemes: frozenset[str] = frozenset({"https", "ssh"})
) -> None:
    """Cheap, synchronous, no-I/O sanity check — rejects obviously bad
    schemes/formats immediately at repository-registration time.

    This is deliberately *not* the authoritative SSRF defense: DNS
    resolution and the private-IP check happen once, in
    `resolve_and_check_ip`, immediately before the real clone (see
    GitPythonAdapter.clone) — checking IPs here and trusting that result
    later would itself be a TOCTOU bug, since DNS can change between
    registering a repository and actually cloning it.

    Only explicit `scheme://host/...` URLs are accepted — scp-like syntax
    (`git@host:org/repo.git`) is rejected because it can't be reliably
    parsed for a hostname to validate.
    """
    parsed = urlsplit(url)
    if parsed.scheme not in allowed_schemes:
        raise RepositoryUrlValidationError(f"Unsupported URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise RepositoryUrlValidationError("URL is missing a hostname")
    if parsed.password is not None:
        raise RepositoryUrlValidationError("URL must not embed a password")
    if parsed.scheme == "https" and parsed.username is not None:
        raise RepositoryUrlValidationError("URL must not embed a username for https")
    expected_port = _ALLOWED_SCHEME_PORTS[parsed.scheme]
    if parsed.port is not None and parsed.port != expected_port:
        raise RepositoryUrlValidationError(
            f"Unexpected port for {parsed.scheme}: {parsed.port} (expected {expected_port})"
        )


async def resolve_and_check_ip(hostname: str) -> None:
    """Resolve `hostname` and reject it if any resolved address is
    private, loopback, link-local (this covers the 169.254.169.254 cloud
    metadata endpoint), reserved, multicast, or unspecified.

    Must be called again on the post-redirect host for any request that
    followed a redirect — DNS rebinding can change resolution between an
    earlier check and the actual connection.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.run_in_executor(None, socket.getaddrinfo, hostname, None)
    except socket.gaierror as exc:
        raise RepositoryUrlValidationError(f"Could not resolve host: {hostname}") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise RepositoryUrlValidationError(
                f"Host {hostname!r} resolves to a disallowed address: {ip}"
            )
