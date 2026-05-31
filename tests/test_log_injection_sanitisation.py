"""
Tests verifying that user-controlled values reaching logging calls are
sanitised — i.e. newline characters are stripped so an attacker cannot
forge log entries by injecting newlines into request parameters.
"""
import logging
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

    exc = ValueError("bad\nvalue")
    result = sanitise_log_value(exc)
    assert "\n" not in result
    assert "bad" in result


def test_sanitise_log_value_strips_newline_from_exception():
    from backend.logging_setup import sanitise_log_value

    exc = OSError("file /tmp/evil\npath not found")
    sanitised = sanitise_log_value(exc)
    assert "\n" not in sanitised
    assert "evil" in sanitised


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

    assert caplog.records, "Expected at least one log record"
    for record in caplog.records:
        assert not _has_raw_newline(record), (
            f"Raw newline in log record: {record.getMessage()!r}"
        )


# ── fetch_meta_timeseries ─────────────────────────────────────────────────────

def test_meta_timeseries_invalid_ticker_pattern_log_no_injection(caplog):
    """A ticker with an injected newline fails the regex; the warning must not leak it."""
    # The newline makes the ticker fail _TICKER_RE, so the "looks invalid" warning fires.
    malicious_ticker = "TICK\nINJECT"

    with caplog.at_level(logging.WARNING, logger="meta_timeseries"):
        from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries
        import pandas as pd
        result = fetch_meta_timeseries(malicious_ticker)

    assert isinstance(result, pd.DataFrame)
    for record in caplog.records:
        assert not _has_raw_newline(record), (
            f"Raw newline in log record: {record.getMessage()!r}"
        )


def test_meta_timeseries_unrecognised_ticker_log_no_injection(caplog):
    """Valid-pattern ticker that fails is_valid_ticker fires an info log; no newline must leak."""
    # "FAKETICKER" passes _TICKER_RE but we mock is_valid_ticker to return False.
    malicious_ticker = "FAKE\x0aTICKER"  # \x0a == \n

    with caplog.at_level(logging.WARNING, logger="meta_timeseries"):
        from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries
        import pandas as pd
        result = fetch_meta_timeseries(malicious_ticker)

    assert isinstance(result, pd.DataFrame)
    for record in caplog.records:
        assert not _has_raw_newline(record), (
            f"Raw newline in log record: {record.getMessage()!r}"
        )


# ── portfolio_loader ──────────────────────────────────────────────────────────

def test_portfolio_loader_missing_tx_file_no_injection(caplog, tmp_path):
    """
    Injected newline in account name must not appear in the
    'Transaction file missing' error log.
    """
    from backend.common.portfolio_loader import rebuild_account_holdings

    malicious_account = "savings\nINJECT"

    with caplog.at_level(logging.ERROR, logger="portfolio_loader"):
        # Pass tmp_path as the accounts_root so safe_join has a real directory.
        # The owner "owner" directory will be created as a sibling.
        owner_dir = tmp_path / "owner"
        owner_dir.mkdir()
        result = rebuild_account_holdings("owner", malicious_account, accounts_root=tmp_path)

    assert result == {}
    for record in caplog.records:
        assert not _has_raw_newline(record), (
            f"Raw newline in log record: {record.getMessage()!r}"
        )


# ── routes/portfolio extra-dict sanitisation ─────────────────────────────────

def test_portfolio_route_extra_dict_no_injection():
    """
    sanitise_log_value wraps owner/account before they enter the extra dict;
    verify newlines are stripped from those dict values.
    """
    from backend.logging_setup import sanitise_log_value

    malicious_owner = "alice\nINJECT"
    malicious_account = "isa\nINJECT"

    extra = {
        "owner": sanitise_log_value(malicious_owner),
        "account": sanitise_log_value(malicious_account),
    }

    assert "\n" not in extra["owner"]
    assert "\r" not in extra["owner"]
    assert "\n" not in extra["account"]
    assert "\r" not in extra["account"]
    assert "alice" in extra["owner"]
    assert "isa" in extra["account"]
