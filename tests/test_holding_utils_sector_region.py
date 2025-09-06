from datetime import date

from backend.common.holding_utils import enrich_holding


def test_enrich_holding_includes_sector_and_region():
    holding = {"ticker": "HFEL.L", "units": 1}
    out = enrich_holding(holding, date.today(), {}, {})
    assert out.get("sector")
    assert out.get("region")
