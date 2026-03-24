from __future__ import annotations

import inspect
import logging
from functools import wraps
from typing import Any, Callable, TypeVar

from fastapi import HTTPException

OWNER_NOT_FOUND = "Owner not found"


class AppError(Exception):
    """Base application error carrying HTTP and observability metadata."""

    status_code = 500
    error_code = "internal_error"
    error_category = "server"  # coarse grouping for alerting/dashboards
    log_level = logging.ERROR
    safe_detail = "Internal server error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        safe_detail: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        internal_detail = detail or self.safe_detail
        response_detail = safe_detail or self.safe_detail
        super().__init__(internal_detail)
        self.detail = internal_detail
        self.safe_detail = response_detail
        self.extra = extra or {}


class ValidationFailure(AppError):
    status_code = 400
    error_code = "validation_failure"
    error_category = "client"
    log_level = logging.WARNING
    safe_detail = "Invalid request"

    def __init__(self, detail: str | None = None, *, extra: dict[str, Any] | None = None) -> None:
        resolved = detail or self.safe_detail
        super().__init__(resolved, safe_detail=resolved, extra=extra)


class ResourceNotFoundError(AppError):
    status_code = 404
    error_code = "not_found"
    error_category = "client"
    log_level = logging.INFO
    safe_detail = "Resource not found"

    def __init__(self, detail: str | None = None, *, extra: dict[str, Any] | None = None) -> None:
        resolved = detail or self.safe_detail
        super().__init__(resolved, safe_detail=resolved, extra=extra)


class PermissionDeniedError(AppError):
    status_code = 403
    error_code = "permission_denied"
    error_category = "client"
    log_level = logging.WARNING
    safe_detail = "Permission denied"


class ProviderFailure(AppError):
    status_code = 502
    error_code = "provider_failure"
    error_category = "provider"
    log_level = logging.ERROR
    safe_detail = "Upstream provider failure"


class InternalServiceError(AppError):
    status_code = 500
    error_code = "internal_service_error"
    error_category = "server"
    log_level = logging.ERROR
    safe_detail = "Internal server error"


class OwnerNotFoundError(ResourceNotFoundError):
    """Raised when a requested owner cannot be located."""

    error_code = "owner_not_found"
    safe_detail = OWNER_NOT_FOUND

    def __init__(self, detail: str = OWNER_NOT_FOUND, *, extra: dict[str, Any] | None = None) -> None:
        super().__init__(detail, extra=extra)


def raise_owner_not_found() -> None:
    """Helper for raising a canonical owner-not-found error."""
    raise OwnerNotFoundError(OWNER_NOT_FOUND)


F = TypeVar("F", bound=Callable[..., Any])


def log_app_error(logger: logging.Logger, exc: AppError, message: str, **context: Any) -> None:
    """Log a structured application error with a consistent taxonomy."""

    extra = {
        "error_code": exc.error_code,
        "error_category": exc.error_category,
        "status_code": exc.status_code,
    }
    if exc.extra:
        extra.update(exc.extra)
    if context:
        extra.update(context)
    logger.log(exc.log_level, "%s [%s]", message, exc.error_code, extra=extra)


def to_http_exception(exc: AppError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.safe_detail)


def handle_app_error(logger: logging.Logger, exc: AppError, message: str, **context: Any) -> HTTPException:
    log_app_error(logger, exc, message, **context)
    return to_http_exception(exc)


def handle_owner_not_found(func: F) -> F:
    """Decorator preserving :class:`OwnerNotFoundError` for app-level handling."""

    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except OwnerNotFoundError:
                raise

        async_wrapper.__signature__ = inspect.signature(func)
        return async_wrapper  # type: ignore[return-value]

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except OwnerNotFoundError:
            raise

    sync_wrapper.__signature__ = inspect.signature(func)
    return sync_wrapper  # type: ignore[return-value]
