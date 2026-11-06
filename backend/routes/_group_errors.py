"""Shared error mapping for the ``/portfolio-group``-style routes (#11428)."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException

from backend.common.data_providers import InvalidPayload


def raise_group_not_found(exc: BaseException) -> NoReturn:
    """Raise 404 "Group not found" for *exc*, unless a data file is unreadable.

    Group builders signal an unknown slug with ``ValueError``. ``InvalidPayload``
    is a ``ValueError`` too, so without this check a corrupt account file was
    reported as a missing group. It is re-raised for the app-wide handler, which
    answers 500 naming the file. Call this from inside the ``except`` block.
    """

    if isinstance(exc, InvalidPayload):
        raise exc
    raise HTTPException(status_code=404, detail="Group not found") from exc
