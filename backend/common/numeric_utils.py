"""Shared numeric helpers for NaN-safe value checks.

Pricing/risk code across the backend repeats the same "is this value
missing" check, split inconsistently between ``math.isnan`` (float-only,
raises ``TypeError`` on ``None``/non-numeric input) and ``pd.isna`` (handles
``None``/``NaT`` but returns an array for array-likes, which is usually not
what a scalar call site wants). :func:`is_nan` centralizes that check for
scalar values.
"""

from __future__ import annotations

import decimal
import math
from typing import Any

import pandas as pd


def is_nan(value: Any) -> bool:
    """Return True if ``value`` is missing: ``None``, float ``NaN``, or ``NaT``.

    Safe for any scalar input, unlike ``math.isnan`` (raises on non-float)
    or bare ``pd.isna`` (returns an array for array-likes rather than a bool
    for a single value). Not intended for array-likes -- use ``pd.isna``
    directly for those.

    ``Decimal`` is short-circuited via ``Decimal.is_nan()`` before reaching
    ``pd.isna``: that method returns True for both quiet and signaling NaN,
    whereas ``pd.isna`` raises ``decimal.InvalidOperation`` on a signaling
    NaN (comparing it against anything is an invalid operation per IEEE 754).
    A signaling NaN is still a NaN, so this is the more correct answer.
    """
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    if isinstance(value, decimal.Decimal):
        return value.is_nan()
    try:
        result = pd.isna(value)
        return bool(result)
    except (TypeError, ValueError, decimal.InvalidOperation):
        # pd.isna raises for some inputs (e.g. dict keys it can't hash) and
        # bool() raises on a multi-element array-like result (ambiguous
        # truth value) -- either way, not a scalar "is this NaN" question,
        # so treat as not-missing rather than propagating the exception.
        return False
