import pytest

from backend.common.sector_labels import (
    CASH_SECTOR_LABEL,
    SECTOR_ALIASES,
    is_cash_instrument,
    normalise_optional_region,
    normalise_optional_sector,
    normalise_sector_label,
)


def test_cash_label_is_never_aliased():
    """Adding a "CASH" alias would silently relabel every cash holding (#8530)."""

    assert CASH_SECTOR_LABEL.upper() not in {key.upper() for key in SECTOR_ALIASES}
    assert normalise_sector_label(CASH_SECTOR_LABEL) == CASH_SECTOR_LABEL
    assert normalise_optional_sector(CASH_SECTOR_LABEL) == CASH_SECTOR_LABEL


@pytest.mark.parametrize("value", [None, "", "   ", 123, 1.5, ["Technology"], {"sector": "Technology"}])
def test_normalise_optional_sector_passes_blank_and_non_string_through_as_none(value):
    assert normalise_optional_sector(value) is None


@pytest.mark.parametrize("value", [None, "", "   ", 123, 1.5, ["UK"], {"region": "UK"}])
def test_normalise_optional_region_passes_blank_and_non_string_through_as_none(value):
    assert normalise_optional_region(value) is None


def test_normalise_optional_helpers_map_aliases_and_keep_unknown_labels():
    assert normalise_optional_sector(" technology ") == "Information Technology"
    assert normalise_optional_sector("Quantum Computing") == "Quantum Computing"
    assert normalise_optional_region("uk") == "United Kingdom"
    assert normalise_optional_region(" North America ") == "North America"


@pytest.mark.parametrize(
    ("ticker", "instrument_type", "expected"),
    [
        ("CASH.GBP", None, True),
        ("cash.usd", None, True),
        ("GBP.CASH", None, True),
        ("CASH", None, True),
        ("XYZ.L", "Cash", True),
        ("CASHX.L", None, False),
        ("HFEL.L", "Equity", False),
        (None, None, False),
    ],
)
def test_is_cash_instrument(ticker, instrument_type, expected):
    assert is_cash_instrument(ticker, instrument_type) is expected
