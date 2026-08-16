"""Stub for the screener engine, which lives in the private ``allotmint-core``
package. See :mod:`backend.common.core_optional` for the degradation pattern
routes should use around this import.
"""

from __future__ import annotations

from backend.common.core_optional import UPGRADE_MESSAGE

try:
    from allotmint_core.screener import (  # noqa: F401
        Fundamentals,
        fetch_fundamentals,
        screen,
    )
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(f"backend.screener requires allotmint-core. {UPGRADE_MESSAGE}") from exc
