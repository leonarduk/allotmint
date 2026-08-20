from datetime import date

from backend.common.holding_utils import enrich_holding


def test_enrich_holding_includes_sector_and_region():
    holding = {"ticker": "HFEL.L", "units": 1}
    out = enrich_holding(holding, date.today(), {}, {})
    assert out.get("sector")
    assert out.get("region")


def test_enrich_holding_instrument_type_falls_back_to_asset_class():
    # VWRL.L's instrument metadata only sets "asset_class" (no
    # "instrumentType"/"instrument_type" key exists in any instrument file
    # in this repo) -- instrument_type must fall back to it rather than
    # come back None, or every Allocation "Instrument Types" chart
    # collapses to "Other". Regression test for #6858.
    holding = {"ticker": "VWRL.L", "units": 1}
    out = enrich_holding(holding, date.today(), {}, {})
    assert out.get("instrument_type") == "Equity"
