from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class InvalidExternalURLError(ValueError):
    """Raised when a URL fails SSRF-safety validation."""


# Hostnames that must always be rejected regardless of how they resolve.
# "ip6-localhost" and "ip6-loopback" are common /etc/hosts aliases for ::1
# on Debian/Ubuntu systems; they are not valid IP literals so _is_private_address
# would not catch them.
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "ip6-localhost",
        "ip6-loopback",
    }
)


def _is_private_address(address: str) -> bool:
    """Return True if *address* is private, loopback, link-local, or reserved.

    Handles standard IPv4/IPv6 literals (e.g. ``192.168.1.1``, ``::1``) and
    abbreviated IPv4 forms (e.g. ``127.1``, ``0x7f000001``, ``2130706433``)
    that ``ipaddress.ip_address`` rejects but the OS socket layer resolves.
    """
    # Standard IPv4 and IPv6 literals.
    try:
        ip = ipaddress.ip_address(address)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    except ValueError:
        pass

    # Abbreviated IPv4 notation (e.g. "127.1" → 127.0.0.1).
    # socket.inet_aton normalises these the same way the OS resolver does,
    # catching bypasses that ipaddress alone would miss.
    try:
        packed = socket.inet_aton(address)
        ip = ipaddress.ip_address(int.from_bytes(packed, "big"))
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    except OSError:
        pass

    return False


def validate_external_url(url: str, *, allow_http: bool = False) -> None:
    """Assert *url* is a safe HTTPS external endpoint.

    Raises :class:`InvalidExternalURLError` when:
    - the scheme is not ``https`` (unless *allow_http* is ``True``);
    - the hostname matches a blocked name (``localhost``, ``ip6-localhost``,
      ``ip6-loopback``, and trailing-dot variants); or
    - the hostname is a *literal* IP address in a private, loopback,
      link-local, or reserved range.

    **Known limitations:**

    * *DNS resolution is not performed.*  A hostname such as
      ``internal.corp.example.com`` that resolves to ``10.0.0.1`` will pass
      this check.  DNS-rebinding and hostname-alias attacks via arbitrary
      domain names are not mitigated here.
    * *Redirects are not validated.*  If the server at the validated URL
      returns a 3xx redirect, callers must pass ``allow_redirects=False`` to
      ``requests.get`` (or otherwise validate the ``Location`` header) to
      prevent redirect-based SSRF.

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
