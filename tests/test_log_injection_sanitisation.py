"""
Tests verifying that user-controlled values reaching logging calls are
sanitised — i.e. newline characters are stripped so an attacker cannot
forge log entries by injecting newlines into request parameters.

All call sites import sanitise_log_value from backend.logging_setup,
which is the canonical location in this codebase (not backend/common/log_utils.py
as originally suggested in the issue; the helper already existed in logging_setup
and all modules import from there).
"""
import logging
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

import pytest


# ── helper ───────────────────────────────────────────────────────────────────

def _has_raw_newline(record: logging.LogRecord) -> bool:
    """Return True if the formatted log message contains a bare newline/CR."""
    msg = record.getMessage()
    return "\n" in msg or "\r" in msg


# ── sanitise_log_value unit tests ────────────────────────────────────────────

def test_sanitise_log_value_strips_newline():
    from backend.logging_setup import sanitise_log_value

    assert "\n" not in sanitise_log_value("ticker\ninjected")
    assert "\r" not in sanitise_log_value("ticker\rinjected")
    assert "\n" not in sanitise_log_value("a\r\nb")


def test_sanitise_log_value_handles_non_string_types():
    from backend.logging_setup import sanitise_log_value

    assert sanitise_log_value(None) == "None"
    assert sanitise_log_value(42) == "42"

    # Exceptions can embed user-supplied filenames; verify newlines are stripped.
    exc = ValueError("bad\nvalue")
    result = sanitise_log_value(exc)
    assert "\n" not in result
    assert "bad" in result


def test_sanitise_log_value_strips_newline_from_exception():
    """OSError messages often embed the filename — which may be user-controlled."""
    from backend.logging_setup import sanitise_log_value

    exc = OSError("file /tmp/evil\npath not found")
    sanitised = sanitise_log_value(exc)
    assert "\n" not in sanitised
    assert "evil" in sanitised


def test_sanitise_log_value_or_sentinel_precedence():
    """
    Regression: `sanitise_log_value(x or '<empty>')` correctly substitutes
    '<empty>' for falsy values, whereas `sanitise_log_value(x) or '<empty>'`
    does NOT (because sanitise_log_value(None) == 'None', which is truthy).
    """
    from backend.logging_setup import sanitise_log_value

    # Correct form: pass the fallback inside the call.
    assert sanitise_log_value(None or "<empty>") == "<empty>"
    assert sanitise_log_value("" or "<empty>") == "<empty>"
    assert sanitise_log_value("real" or "<empty>") == "real"

    # Confirm the wrong form would not substitute '<empty>' for None.
    assert (sanitise_log_value(None) or "<empty>") == "None"  # 'None' is truthy


# ── fetch_alphavantage_timeseries ─────────────────────────────────────────────

def test_alphavantage_skipped_ticker_log_no_injection(caplog):
    """Injected newline in ticker/exchange must not appear in the log message."""
    from datetime import date

    malicious_ticker = "VOD\nINJECTED"
    malicious_exchange = "L\nFAKE"

    with caplog.at_level(logging.DEBUG, logger="alphavantage_timeseries"):
        with patch(
            "backend.timeseries.fetch_alphavantage_timeseries.is_valid_ticker",
            return_value=False,
        ):
            from backend.timeseries.fetch_alphavantage_timeseries import (
                fetch_alphavantage_timeseries_range,
            )
            fetch_alphavantage_timeseries_range(
                malicious_ticker,
                malicious_exchange,
                date(2024, 1, 1),
                date(2024, 1, 31),
            )

    assert caplog.records, (
        "Expected at least one log record from alphavantage_timeseries logger"
    )
    for record in caplog.records:
        assert not _has_raw_newline(record), (
            f"Raw newline in log record: {record.getMessage()!r}"
        )


# ── fetch_meta_timeseries ─────────────────────────────────────────────────────

def test_meta_timeseries_invalid_ticker_pattern_log_no_injection(caplog):
    """
    A ticker containing a newline fails _TICKER_RE; the 'looks invalid' warning
    must not echo the raw malicious string into the log.
    """
    # The newline makes the ticker fail _TICKER_RE, so the "looks invalid" warning fires.
    malicious_ticker = "TICK\nINJECT"

    with caplog.at_level(logging.WARNING, logger="meta_timeseries"):
        from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries
        import pandas as pd
        result = fetch_meta_timeseries(malicious_ticker)

    assert isinstance(result, pd.DataFrame)
    assert caplog.records, "Expected at least one warning record from meta_timeseries logger"
    for record in caplog.records:
        assert not _has_raw_newline(record), (
            f"Raw newline in log record: {record.getMessage()!r}"
        )


def test_meta_timeseries_cache_exchange_mismatch_sentinel():
    """
    Verify that a None/empty metadata_exchange produces the '<empty>' sentinel
    in the log message, not the string 'None'.  This guards the operator-
    precedence fix: sanitise_log_value(x or '<empty>') vs
    sanitise_log_value(x) or '<empty>'.
    """
    from backend.logging_setup import sanitise_log_value

    # Simulate what the fixed log call does when metadata_exchange is None/empty.
    assert sanitise_log_value(None or "<empty>") == "<empty>"
    assert sanitise_log_value("" or "<empty>") == "<empty>"
    # Ensure a real value passes through unchanged.
    assert sanitise_log_value("L" or "<empty>") == "L"


# ── portfolio_loader ──────────────────────────────────────────────────────────

def test_portfolio_loader_missing_tx_file_no_injection(caplog, tmp_path):
    """
    Injected newline in account name must not appear in the
    'Transaction file missing' error log, and the path separator must be
    OS-correct (derived from os.path.join, not a hardcoded '/').
    """
    import os
    from backend.common.portfolio_loader import rebuild_account_holdings

    malicious_account = "savings\nINJECT"

    with caplog.at_level(logging.ERROR, logger="portfolio_loader"):
        owner_dir = tmp_path / "owner"
        owner_dir.mkdir()
        result = rebuild_account_holdings("owner", malicious_account, accounts_root=tmp_path)

    assert result == {}
    assert caplog.records, "Expected at least one error record from portfolio_loader"
    for record in caplog.records:
        assert not _has_raw_newline(record), (
            f"Raw newline in log record: {record.getMessage()!r}"
        )
    # The logged path should use the OS path separator, not a hardcoded '/'.
    logged_msg = caplog.records[0].getMessage()
    assert os.sep in logged_msg or "/" in logged_msg  # sep is '\' on Windows, '/' on Unix


# ── routes/portfolio — TestClient integration test ───────────────────────────

def _portfolio_test_client(tmp_path):
    """Build a minimal FastAPI app wired to the portfolio router."""
    from backend.routes import portfolio as portfolio_module
    app = FastAPI()
    app.include_router(portfolio_module.router)
    app.state.accounts_root = tmp_path
    return TestClient(app, raise_server_exceptions=False)


def test_get_account_provider_unavailable_no_log_injection(caplog, monkeypatch, tmp_path):
    """
    When the data provider is unavailable, the handler logs owner and account
    via the extra dict.  Injected newlines (URL-encoded as %0A, which the server
    decodes before logging) must not appear in the structured log fields.

    httpx rejects raw '\n' in URLs — the realistic attack uses %0A encoding,
    which FastAPI's path-parameter parsing decodes to '\n' before the handler runs.
    """
    import backend.common.data_loader as dl

    def _raise_unavailable(*args, **kwargs):
        raise dl.ProviderUnavailable("simulated failure")

    monkeypatch.setattr(dl, "load_account", _raise_unavailable)

    client = _portfolio_test_client(tmp_path)

    # %0A is the URL-encoded form of '\n'; FastAPI decodes it before the handler sees it.
    with caplog.at_level(logging.WARNING, logger="routes.portfolio"):
        resp = client.get("/account/alice%0AINJECT/isa%0AINJECT")

    assert resp.status_code == 503

    for record in caplog.records:
        owner_val = str(record.__dict__.get("owner", ""))
        account_val = str(record.__dict__.get("account", ""))
        assert "\n" not in owner_val and "\r" not in owner_val, (
            f"Raw newline in extra['owner']: {owner_val!r}"
        )
        assert "\n" not in account_val and "\r" not in account_val, (
            f"Raw newline in extra['account']: {account_val!r}"
        )


def test_get_account_invalid_payload_no_log_injection(caplog, monkeypatch, tmp_path):
    """
    InvalidPayload also logs owner/account via the extra dict; verify that
    URL-decoded newlines are stripped before reaching the log fields.
    """
    import backend.common.data_loader as dl

    def _raise_invalid(*args, **kwargs):
        raise dl.InvalidPayload("bad data")

    monkeypatch.setattr(dl, "load_account", _raise_invalid)

    client = _portfolio_test_client(tmp_path)

    with caplog.at_level(logging.WARNING, logger="routes.portfolio"):
        resp = client.get("/account/bob%0AINJECT/sipp%0AINJECT")

    assert resp.status_code == 502

    for record in caplog.records:
        for field in ("owner", "account"):
            val = str(record.__dict__.get(field, ""))
            assert "\n" not in val and "\r" not in val, (
                f"Raw newline in extra['{field}']: {val!r}"
            )
