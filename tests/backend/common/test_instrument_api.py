from backend.common import instrument_api


def test_derive_grouping_prefers_sector_over_currency():
    meta = {"sector": "Technology", "currency": "USD"}

    assert instrument_api._derive_grouping(meta) == "Technology"


def test_derive_grouping_prefers_currency_over_region():
    meta = {"currency": "EUR", "region": "Europe"}

    assert instrument_api._derive_grouping(meta) == "EUR"
