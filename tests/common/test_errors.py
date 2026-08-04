import asyncio
import logging

import pytest

from backend.common import errors as errors_module
from backend.common.errors import (
    OWNER_NOT_FOUND,
    OwnerNotFoundError,
    ProviderFailure,
    ValidationFailure,
    handle_app_error,
    handle_owner_not_found,
    log_owner_not_found,
    raise_owner_not_found,
    to_http_exception,
)


def test_log_owner_not_found_strips_newlines_but_keeps_quotes_in_diagnostics(caplog):
    """Special characters (quotes, newlines) in a diagnostic value must not
    break or truncate the log line: newlines are stripped by
    ``sanitise_log_value`` (CWE-117 log injection defence), but quotes are
    left untouched -- they aren't part of what that helper sanitises (#5884)."""
    with caplog.at_level(logging.WARNING, logger="backend.common.errors"):
        log_owner_not_found("ghost", note='has "quotes" and\nnewlines\r\nhere')

    assert 'owner lookup: no owner found for owner=ghost (note=has "quotes" andnewlineshere)' in caplog.text


def test_log_owner_not_found_sanitises_each_value_exactly_once(monkeypatch, caplog):
    """Regression for #5879/#5880: the assembled ``suffix`` string must not be
    passed through ``sanitise_log_value`` a second time on top of the
    per-diagnostic-value sanitisation already applied when building it."""
    call_count = 0
    real_sanitise = errors_module.sanitise_log_value

    def counting_sanitise(value):
        nonlocal call_count
        call_count += 1
        return real_sanitise(value)

    monkeypatch.setattr(errors_module, "sanitise_log_value", counting_sanitise)

    with caplog.at_level(logging.WARNING, logger="backend.common.errors"):
        log_owner_not_found("ghost", diag_a="x", diag_b="y")

    # once for `owner`, once per diagnostic value -- never once more for the
    # assembled suffix string as a whole.
    assert call_count == 3
    assert "owner lookup: no owner found for owner=ghost (diag_a=x, diag_b=y)" in caplog.text


def test_raise_owner_not_found(caplog):
    with caplog.at_level(logging.WARNING, logger="backend.common.errors"):
        with pytest.raises(OwnerNotFoundError) as excinfo:
            raise_owner_not_found("missing-owner", total_plots_discovered=3)
    assert str(excinfo.value) == OWNER_NOT_FOUND
    assert excinfo.value.extra == {
        "owner": "missing-owner",
        "total_plots_discovered": 3,
    }
    assert "owner lookup: no owner found for owner=missing-owner " "(total_plots_discovered=3)" in caplog.text


def test_handle_owner_not_found_sync():
    @handle_owner_not_found
    def sample(ok: bool):
        if ok:
            return "ok"
        raise_owner_not_found()

    assert sample(True) == "ok"
    with pytest.raises(OwnerNotFoundError) as excinfo:
        sample(False)
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == OWNER_NOT_FOUND


def test_handle_owner_not_found_async():
    @handle_owner_not_found
    async def sample(ok: bool):
        if ok:
            return "ok"
        raise_owner_not_found()

    assert asyncio.run(sample(True)) == "ok"
    with pytest.raises(OwnerNotFoundError) as excinfo:
        asyncio.run(sample(False))
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == OWNER_NOT_FOUND


def test_handle_app_error_logs_structured_fields(caplog):
    logger = logging.getLogger("tests.errors")
    exc = ProviderFailure("provider blew up", extra={"provider": "yfinance"})

    with caplog.at_level(logging.ERROR, logger="tests.errors"):
        http_exc = handle_app_error(logger, exc, "Quote fetch failed", route="/api/quotes")

    assert http_exc.status_code == 502
    assert http_exc.detail == "Upstream provider failure"
    assert caplog.records
    record = caplog.records[-1]
    assert record.error_code == "provider_failure"
    assert record.error_category == "provider"  # coarse grouping, not a copy of error_code
    assert record.status_code == 502
    assert record.provider == "yfinance"
    assert record.route == "/api/quotes"


def test_validation_failure_uses_caller_detail_for_http_response():
    exc = ValidationFailure("Ticker is required", extra={"field": "ticker"})

    http_exc = to_http_exception(exc)

    assert http_exc.status_code == 400
    assert http_exc.detail == "Ticker is required"
    assert exc.detail == "Ticker is required"
    assert exc.safe_detail == "Ticker is required"


def test_provider_failure_keeps_internal_detail_out_of_http_response():
    exc = ProviderFailure("Failed to fetch quotes: boom", extra={"provider_error": "boom"})

    http_exc = to_http_exception(exc)

    assert http_exc.status_code == 502
    assert http_exc.detail == "Upstream provider failure"
    assert exc.detail == "Failed to fetch quotes: boom"
    assert exc.safe_detail == "Upstream provider failure"
