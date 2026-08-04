import math

import pytest

from backend.common.numeric_utils import clean_price


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        (float("nan"), None),
        ("nan", None),
        (10, 10.0),
        ("12.5", 12.5),
        (0, 0.0),
        ("not-a-number", None),
        (object(), None),
    ],
)
def test_clean_price(value, expected):
    result = clean_price(value)
    if expected is None:
        assert result is None
    else:
        assert result == expected


def test_clean_price_rejects_infinity_is_not_special_cased():
    # clean_price only guards NaN; +/-inf pass through as floats since callers
    # treat them the same as any other unusable-but-not-NaN price.
    assert clean_price(float("inf")) == float("inf")
    assert not math.isnan(clean_price(float("inf")))
