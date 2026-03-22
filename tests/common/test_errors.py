import asyncio
import logging

import pytest
from fastapi import HTTPException

from backend.common.errors import (
    OWNER_NOT_FOUND,
    OwnerNotFoundError,
    ProviderFailure,
    handle_app_error,
    handle_owner_not_found,
    raise_owner_not_found,
)


def test_raise_owner_not_found():
    with pytest.raises(OwnerNotFoundError) as excinfo:
        raise_owner_not_found()
    assert str(excinfo.value) == OWNER_NOT_FOUND


def test_handle_owner_not_found_sync():
    @handle_owner_not_found
    def sample(ok: bool):
        if ok:
            return "ok"
        raise_owner_not_found()

    assert sample(True) == "ok"
    with pytest.raises(HTTPException) as excinfo:
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
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(sample(False))
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == OWNER_NOT_FOUND


def test_handle_app_error_logs_structured_fields(caplog):
    logger = logging.getLogger("tests.errors")
    exc = ProviderFailure("provider blew up", extra={"provider": "yfinance"})

    with caplog.at_level(logging.ERROR, logger="tests.errors"):
        http_exc = handle_app_error(logger, exc, "Quote fetch failed", route="/api/quotes")

    assert http_exc.status_code == 502
    assert http_exc.detail == "provider blew up"
    assert caplog.records
    record = caplog.records[-1]
    assert record.error_code == "provider_failure"
    assert record.error_category == "provider_failure"
    assert record.status_code == 502
    assert record.provider == "yfinance"
    assert record.route == "/api/quotes"
