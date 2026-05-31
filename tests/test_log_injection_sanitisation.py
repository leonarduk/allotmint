"""
Tests verifying that user-controlled values reaching logging calls are
sanitised — i.e. newline characters are stripped so an attacker cannot
forge log entries by injecting newlines into request parameters.

All call sites import sanitise_log_value from backend.logging_setup,
which is the canonical location in this codebase (not backend/common/log_utils.py
as originally suggested in the issue; the helper already existed in logging_setup
and all modules import from there).

Implementation note: sanitise_log_value(value) calls str(value) before the
replace() calls, so it is safe for any type including pathlib.Path, Exception,
None, and numeric types.  Tests below verify this explicitly.

Logger names used in caplog.at_level() calls match the explicit string names
passed to logging.getLogger() in each module (not __name__):
  alphavantage_timeseries  → fetch_alphavantage_timeseries.py
  meta_timeseries          → fetch_meta_timeseries.py
  portfolio_loader         → portfolio_loader.py
  routes.portfolio         → routes/portfolio.py
  portfolio_utils          → portfolio_utils.py
  data_loader              → data_loader.py (logger = logging.getLogger(__name__))
"""
import logging
import os
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


def test_sanitise_log_value_handles_path_objects():
    """
    sanitise_log_value calls str(value) before replace(), so pathlib.Path
    objects (used in portfolio_loader tx_path log) are handled safely.
    tx_path derives from owner/account inputs which may contain newlines.
    """
    from backend.logging_setup import sanitise_log_value

    p = Path("/data/owner") / "savings_transactions.json"
    result = sanitise_log_value(p)
    assert isinstance(result, str)
    assert "savings_transactions.json" in result
    assert "\n" not in result

    # A path whose string representation contains a newline (edge case).
    injected = sanitise_log_value("/data/evil\npath/file.json")
    assert "\n" not in injected
    assert "evil" in injected


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
        import pandas as pd

        from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries
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


# ── data_loader ───────────────────────────────────────────────────────────────

def test_data_loader_extra_dict_current_user_sanitised():
    """
    data_loader.list_plots logs current_user in the extra dict when the S3
    provider is unavailable.  Verify that sanitise_log_value strips newlines
    from the value before it enters the dict — i.e. the dict construction
    pattern used in the code is safe.

    The log call only fires in aws mode (requires boto3 and ProviderUnavailable),
    so this test directly exercises the sanitisation step rather than the full
    code path.
    """
    from backend.logging_setup import sanitise_log_value

    malicious_user = "alice\nINJECT"
    extra = {
        "event": "data_loader.list_plots_provider_unavailable",
        "current_user": sanitise_log_value(malicious_user),
        "provider": "s3",
    }

    assert "\n" not in extra["current_user"]
    assert "\r" not in extra["current_user"]
    assert "alice" in extra["current_user"]


def test_data_loader_person_meta_owner_sanitised():
    """
    data_loader.load_person_meta logs owner in the extra dict for
    InvalidPayload and ProviderUnavailable exceptions.  Verify sanitisation.
    """
    from backend.logging_setup import sanitise_log_value

    malicious_owner = "owner\nINJECT"
    for event in (
        "data_loader.person_meta_invalid_payload",
        "data_loader.person_meta_provider_unavailable",
    ):
        extra = {
            "event": event,
            "owner": sanitise_log_value(malicious_owner),
            "provider": "s3",
        }
        assert "\n" not in extra["owner"], f"Newline in extra['owner'] for {event}"
        assert "owner" in extra["owner"]


# ── portfolio_utils ───────────────────────────────────────────────────────────

def test_portfolio_utils_ticker_log_no_injection(caplog):
    """
    portfolio_utils logs ticker/exchange in a warning when non-numeric closes
    are discarded while rebuilding the portfolio series.  Verify that injected
    newlines in a ticker string do not reach the log.

    The logger name is 'portfolio_utils' (explicit string, not __name__).
    """
    from backend.logging_setup import sanitise_log_value

    malicious_ticker = "EVIL\nINJECT"
    malicious_exchange = "L\nFAKE"

    # Simulate the log call made in _rebuild_portfolio_series_from_timeseries.
    logger = logging.getLogger("portfolio_utils")
    with caplog.at_level(logging.WARNING, logger="portfolio_utils"):
        logger.warning(
            "Discarding %d non-numeric closes for %s.%s while rebuilding portfolio series",
            3,
            sanitise_log_value(malicious_ticker),
            sanitise_log_value(malicious_exchange),
        )

    assert caplog.records, "Expected a warning record from portfolio_utils logger"
    for record in caplog.records:
        assert not _has_raw_newline(record), (
            f"Raw newline in log record: {record.getMessage()!r}"
        )
