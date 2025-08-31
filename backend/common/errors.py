from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable, TypeVar

from fastapi import HTTPException

OWNER_NOT_FOUND = "Owner not found"


class OwnerNotFoundError(Exception):
    """Raised when a requested owner cannot be located."""


def raise_owner_not_found() -> None:
    """Helper for raising a canonical owner-not-found error."""
    raise OwnerNotFoundError(OWNER_NOT_FOUND)


F = TypeVar("F", bound=Callable[..., Any])


def handle_owner_not_found(func: F) -> F:
    """Decorator mapping :class:`OwnerNotFoundError` to ``HTTPException(404)``."""

    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except OwnerNotFoundError as exc:  # pragma: no cover - thin wrapper
                raise HTTPException(status_code=404, detail=OWNER_NOT_FOUND) from exc
        async_wrapper.__globals__.update(func.__globals__)
        async_wrapper.__signature__ = inspect.signature(func)
        return async_wrapper  # type: ignore[return-value]

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except OwnerNotFoundError as exc:  # pragma: no cover - thin wrapper
            raise HTTPException(status_code=404, detail=OWNER_NOT_FOUND) from exc
    sync_wrapper.__globals__.update(func.__globals__)
    sync_wrapper.__signature__ = inspect.signature(func)
    return sync_wrapper  # type: ignore[return-value]
