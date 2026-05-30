from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


class InvalidExternalURLError(ValueError):
    """Raised when a URL fails SSRF-safety validation."""


_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({"localhost"})


def _is_private_address(address: str) -> bool:
    """Return True if *address* is private, loopback, link-local, or reserved."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_external_url(url: str, *, allow_http: bool = False) -> None:
    """Assert *url* is a safe HTTPS external endpoint.

    Raises :class:`InvalidExternalURLError` when:
    - the scheme is not ``https`` (unless *allow_http* is ``True``);
    - the hostname is ``localhost`` or similar blocked name; or
    - the hostname is a literal IP in a private/loopback/link-local range.

    Call this at the point each configurable URL is first used, not at
    config load time, so that values modified after startup are also caught.
    """
    parsed = urlparse(url)
    allowed_schemes: frozenset[str] = (
        frozenset({"https", "http"}) if allow_http else frozenset({"https"})
    )
    if parsed.scheme not in allowed_schemes:
        allowed_desc = "https or http" if allow_http else "https"
        raise InvalidExternalURLError(
            f"Disallowed URL scheme {parsed.scheme!r}; only {allowed_desc} is permitted"
        )

    hostname = parsed.hostname
    if not hostname:
        raise InvalidExternalURLError(f"URL contains no hostname: {url!r}")

    # Strip a trailing dot (valid DNS absolute-name syntax) before the
    # blocked-hostname check, so "localhost." cannot bypass the list.
    if hostname.lower().rstrip(".") in _BLOCKED_HOSTNAMES:
        raise InvalidExternalURLError(
            f"Hostname {hostname!r} is not permitted for external requests"
        )

    if _is_private_address(hostname):
        raise InvalidExternalURLError(
            f"IP address {hostname!r} is in a private or reserved range"
        )
