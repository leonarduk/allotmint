from __future__ import annotations

import pytest

from backend.common.url_validator import InvalidExternalURLError, validate_external_url

# ── scheme enforcement ────────────────────────────────────────────────────────

def test_https_url_passes():
    validate_external_url("https://api.example.com/query?key=abc")


def test_http_rejected_by_default():
    with pytest.raises(InvalidExternalURLError, match="scheme"):
        validate_external_url("http://api.example.com/query")


def test_http_allowed_when_flag_set():
    validate_external_url("http://api.example.com/query", allow_http=True)


def test_ftp_rejected():
    with pytest.raises(InvalidExternalURLError, match="scheme"):
        validate_external_url("ftp://files.example.com/data")


def test_no_scheme_rejected():
    with pytest.raises(InvalidExternalURLError):
        validate_external_url("//api.example.com/query")


# ── blocked hostnames ─────────────────────────────────────────────────────────

def test_localhost_rejected():
    with pytest.raises(InvalidExternalURLError, match="not permitted"):
        validate_external_url("https://localhost/api")


def test_localhost_with_port_rejected():
    with pytest.raises(InvalidExternalURLError, match="not permitted"):
        validate_external_url("https://localhost:8080/api")


def test_localhost_trailing_dot_rejected():
    # "localhost." is valid absolute-DNS syntax; urlparse returns "localhost."
    # as the hostname, so the blocklist check must strip the trailing dot.
    with pytest.raises(InvalidExternalURLError, match="not permitted"):
        validate_external_url("https://localhost./api")


def test_ip6_localhost_rejected():
    # ip6-localhost is a common /etc/hosts alias for ::1 on Debian/Ubuntu;
    # it is not a valid IP literal so _is_private_address would not catch it.
    with pytest.raises(InvalidExternalURLError, match="not permitted"):
        validate_external_url("https://ip6-localhost/api")


def test_ip6_loopback_rejected():
    with pytest.raises(InvalidExternalURLError, match="not permitted"):
        validate_external_url("https://ip6-loopback/api")


# ── private IP ranges ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "url",
    [
        pytest.param("https://127.0.0.1/api", id="loopback_ipv4"),
        pytest.param("https://127.1.2.3/api", id="loopback_ipv4_variant"),
        pytest.param("https://169.254.169.254/latest/meta-data/", id="link_local_aws_metadata"),
        pytest.param("https://169.254.0.1/path", id="link_local_generic"),
        pytest.param("https://10.0.0.1/internal", id="rfc1918_10_block"),
        pytest.param("https://10.255.255.255/internal", id="rfc1918_10_block_end"),
        pytest.param("https://172.16.0.1/internal", id="rfc1918_172_start"),
        pytest.param("https://172.31.255.255/internal", id="rfc1918_172_end"),
        pytest.param("https://192.168.1.1/router", id="rfc1918_192_168"),
        pytest.param("https://0.0.0.0/api", id="unspecified"),
        pytest.param("https://[::1]/api", id="loopback_ipv6"),
        pytest.param("https://[fe80::1]/api", id="link_local_ipv6"),
    ],
)
def test_private_ip_rejected(url: str) -> None:
    with pytest.raises(InvalidExternalURLError, match="private or reserved"):
        validate_external_url(url)


# ── valid public endpoints ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "url",
    [
        pytest.param("https://www.alphavantage.co/query", id="alphavantage"),
        pytest.param("https://query1.finance.yahoo.com/v1/finance/search", id="yahoo_finance"),
        pytest.param("https://news.google.com/rss/search", id="google_news"),
        pytest.param("https://paper-api.alpaca.markets/v2/account/activities/trades", id="alpaca"),
        pytest.param("https://8.8.8.8/api", id="public_ip"),
    ],
)
def test_public_url_passes(url: str) -> None:
    validate_external_url(url)


# ── allow_http does not bypass IP-range check ─────────────────────────────────

def test_allow_http_does_not_bypass_ip_check():
    # allow_http=True relaxes the scheme requirement only; private IPs must
    # still be rejected so that an attacker cannot reach internal services
    # over plain HTTP even when the flag is set.
    with pytest.raises(InvalidExternalURLError, match="private or reserved"):
        validate_external_url("http://127.0.0.1/api", allow_http=True)


def test_allow_http_does_not_bypass_localhost_check():
    with pytest.raises(InvalidExternalURLError, match="not permitted"):
        validate_external_url("http://localhost/api", allow_http=True)


# ── missing hostname ──────────────────────────────────────────────────────────

def test_no_hostname_rejected():
    with pytest.raises(InvalidExternalURLError, match="no hostname"):
        validate_external_url("https:///path")
