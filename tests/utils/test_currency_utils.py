import pytest
from backend.utils.currency_utils import currency_from_isin


def test_known_prefixes():
    assert currency_from_isin("GB0000000001") == "GBP"
    assert currency_from_isin("US0000000001") == "USD"


def test_unknown_prefix_defaults_to_gbp():
    assert currency_from_isin("ZZ0000000001") == "GBP"
    assert currency_from_isin("") == "GBP"
