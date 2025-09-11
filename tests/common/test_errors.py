import asyncio
import pytest
from fastapi import HTTPException

from backend.common.errors import (
    OWNER_NOT_FOUND,
    OwnerNotFoundError,
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
