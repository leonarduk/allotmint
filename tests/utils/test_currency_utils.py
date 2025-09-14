import pytest

from backend.utils.currency_utils import currency_from_isin


@pytest.mark.parametrize(
    "isin,expected",
    [
        ("GB00B03MLX29", "GBP"),
        ("us0378331005", "USD"),
        ("XX0000000000", "GBP"),
    ],
)
def test_currency_from_isin(isin, expected):
    """Known and unknown ISIN prefixes map to correct currencies."""
    assert currency_from_isin(isin) == expected
