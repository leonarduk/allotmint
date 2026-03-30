from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any


def _coerce_numeric(candidate: Any) -> float | None:
    if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
        return float(candidate)
    return None


def extract_var_value(payload: Any) -> float | None:
    """Extract a numeric VaR value from supported payload shapes."""

    if not isinstance(payload, dict):
        return None

    for key in ("var", "var_pct", "value_at_risk"):
        numeric = _coerce_numeric(payload.get(key))
        if numeric is not None:
            return numeric

    nested_var = payload.get("var")
    if not isinstance(nested_var, dict):
        return None

    for horizon in ("1d", "10d"):
        numeric = _coerce_numeric(nested_var.get(horizon))
        if numeric is not None:
            return numeric

    horizon_candidates: list[tuple[int, float]] = []
    for nested_key, nested_value in nested_var.items():
        if nested_key in ("window_days", "confidence"):
            continue
        if not re.fullmatch(r"\d+d", str(nested_key)):
            continue
        numeric = _coerce_numeric(nested_value)
        if numeric is None:
            continue
        day_count = int(str(nested_key)[:-1])
        horizon_candidates.append((day_count, numeric))

    if not horizon_candidates:
        return None

    horizon_candidates.sort(key=lambda pair: pair[0])
    return horizon_candidates[0][1]


def _contains_null_or_non_finite(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_null_or_non_finite(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_null_or_non_finite(child) for child in value)
    return False


def validate_var_payload(payload: Any) -> None:
    """Validate strict-runner VaR payload rules and raise on invalid data."""

    if _contains_null_or_non_finite(payload):
        raise ValueError("VaR payload contains NaN/null")

    value = extract_var_value(payload)
    if value is None:
        raise ValueError("VaR numeric value not found")
    if not math.isfinite(value) or value <= 0:
        raise ValueError("VaR must be finite and > 0")


def validate_var_payload_file(path: str | Path) -> None:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    validate_var_payload(payload)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/qa/var_payload_validator.py <path-to-json>")
    validate_var_payload_file(sys.argv[1])
