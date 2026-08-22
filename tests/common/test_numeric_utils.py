from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from backend.common.numeric_utils import is_nan


@pytest.mark.parametrize(
    "value",
    [
        None,
        float("nan"),
        np.nan,
        pd.NaT,
        Decimal("NaN"),
    ],
)
def test_is_nan_true_for_missing_values(value) -> None:
    assert is_nan(value) is True


@pytest.mark.parametrize(
    "value",
    [
        0,
        0.0,
        1,
        -1.5,
        "",
        "abc",
        "NaN",
        Decimal("1.5"),
        pd.Timestamp("2024-01-01"),
        True,
        False,
    ],
)
def test_is_nan_false_for_non_missing_values(value) -> None:
    assert is_nan(value) is False


def test_is_nan_handles_unhashable_or_uncomparable_gracefully() -> None:
    """pd.isna raises for some array-likes (e.g. multi-element ndarrays);
    is_nan is documented as scalar-only but must not blow up the caller."""
    assert is_nan([1, 2, 3]) is False


@pytest.mark.parametrize(
    "value",
    [
        Decimal("sNaN"),
        Decimal("-sNaN"),
        Decimal("NaN"),
    ],
)
def test_is_nan_true_for_signaling_decimal_nan(value) -> None:
    """A signaling Decimal NaN must not raise decimal.InvalidOperation and
    must be reported as missing, same as a quiet NaN (#6084)."""
    assert is_nan(value) is True


def test_is_nan_false_for_finite_decimal() -> None:
    assert is_nan(Decimal("42.5")) is False
