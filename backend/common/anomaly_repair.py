"""Stub for the flash-crash anomaly-repair heuristic, which lives in the
private ``allotmint-core`` package. See :mod:`backend.common.core_optional`
for the degradation pattern routes should use around this import.
"""

from __future__ import annotations

from backend.common.core_optional import UPGRADE_MESSAGE

try:
    from allotmint_core.anomaly_repair import _detect_single_day_flash_crash  # noqa: F401
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(f"backend.common.anomaly_repair requires allotmint-core. {UPGRADE_MESSAGE}") from exc
