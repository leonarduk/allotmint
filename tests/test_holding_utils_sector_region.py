import shutil
from datetime import date
from pathlib import Path

import pytest

from backend.common.holding_utils import enrich_holding
from backend.timeseries import cache as ts_cache

_FIXTURE_META = Path(__file__).resolve().parent / "data" / "timeseries" / "meta"


@pytest.fixture(autouse=True)
def _fixture_price_cache(monkeypatch, tmp_path):
    """Serve these tickers' prices from the checked-in fixture parquets.

    enrich_holding prices the holding. With nothing cached for the ticker,
    offline mode raised "no cache available" - so these tests passed only
    when an earlier test in the same process had already cached it, and
    failed on their own or on a pytest-xdist worker that hadn't.
    """
    meta = tmp_path / "meta"
    meta.mkdir()
    for name in ("HFEL_L.parquet", "VWRL_L.parquet"):
        shutil.copy(_FIXTURE_META / name, meta / name)
    monkeypatch.setattr(ts_cache, "_CACHE_BASE", str(tmp_path))
    ts_cache._memoized_range_cached.cache_clear()
    ts_cache._load_meta_timeseries_cached.cache_clear()
    yield
    ts_cache._memoized_range_cached.cache_clear()
    ts_cache._load_meta_timeseries_cached.cache_clear()


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
    assert out.get("instrument_type") == "equity"


@pytest.mark.parametrize("stored", ["Equity", "equity", " EQUITY "])
def test_enrich_holding_canonicalises_legacy_asset_class(monkeypatch, stored):
    # Instrument metadata persisted before #9196 (e.g. a stale S3 copy or an
    # un-backfilled live data root) spells the asset class "Equity". It must
    # enrich exactly like a reclassified "equity" record.
    from backend.common import holding_utils

    monkeypatch.setattr(
        holding_utils,
        "get_instrument_meta",
        lambda t: {"name": "Vanguard FTSE All-World", "asset_class": stored} if t == "VWRL.L" else {},
    )
    out = enrich_holding({"ticker": "VWRL.L", "units": 1}, date.today(), {}, {})
    assert out["asset_class"] == "equity"
    assert out["instrument_type"] == "equity"


_LEGACY_ETF_META = {
    "name": "Vanguard FTSE All-World UCITS ETF",
    "instrumentType": "ETF",
    "asset_class": "Equity",
    "sector": "Financials",
}


def _patch_instrument_meta(monkeypatch, metas):
    """Serve ``metas`` from both enrich_holding's and get_security_meta's lookups."""
    from backend.common import holding_utils, portfolio_utils

    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda t: metas.get(t, {}))
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda t: metas.get(t, {}))
    monkeypatch.setattr(portfolio_utils, "_SECURITIES", None)


def test_enrich_holding_corrects_legacy_issuer_sector_on_fund(monkeypatch):
    # Un-backfilled metadata (stale S3 copy / live data root) still files the
    # ETF under its issuer's sector. Read-time correction gives its exposure
    # sector, and the legacy "Equity" asset class comes out canonical (#9196).
    _patch_instrument_meta(monkeypatch, {"VWRL.L": _LEGACY_ETF_META})
    out = enrich_holding({"ticker": "VWRL.L", "units": 1}, date.today(), {}, {})
    assert out["sector"] == "Multi-sector"
    assert out["asset_class"] == "equity"
    assert out["instrument_type"] == "ETF"


def test_enrich_holding_corrects_issuer_sector_carried_on_the_holding(monkeypatch):
    # An HL export can put the issuer sector on the holding row itself.
    _patch_instrument_meta(monkeypatch, {"VWRL.L": {**_LEGACY_ETF_META, "sector": None}})
    out = enrich_holding({"ticker": "VWRL.L", "units": 1, "sector": "Financial Services"}, date.today(), {}, {})
    assert out["sector"] == "Multi-sector"


def test_enrich_holding_keeps_financials_on_a_bank_share(monkeypatch):
    bank = {"name": "Lloyds Banking Group plc", "instrumentType": "Equity", "asset_class": "Equity"}
    _patch_instrument_meta(monkeypatch, {"LLOY.L": {**bank, "sector": "Financials"}})
    out = enrich_holding({"ticker": "LLOY.L", "units": 0}, date.today(), {}, {})
    assert out["sector"] == "Financials"
    assert out["asset_class"] == "equity"


def test_enrich_holding_normalises_sector_and_region_aliases():
    # Per-holding rows feed /allocation directly, so they must carry the same
    # canonical labels as the backend aggregates (#8530).
    holding = {"ticker": "HFEL.L", "units": 1, "sector": "Financial Services", "region": "UK"}
    out = enrich_holding(holding, date.today(), {}, {})
    assert out["sector"] == "Financials"
    assert out["region"] == "United Kingdom"


def test_enrich_holding_keeps_real_estate_services_distinct():
    holding = {"ticker": "HFEL.L", "units": 1, "sector": "Real Estate Services"}
    out = enrich_holding(holding, date.today(), {}, {})
    assert out["sector"] == "Real Estate Services"


def test_enrich_holding_labels_cash_sector():
    holding = {"ticker": "CASH.GBP", "units": 100, "region": "UK"}
    out = enrich_holding(holding, date.today(), {}, {})
    assert out["sector"] == "Cash"
    assert out["region"] == "United Kingdom"


def test_enrich_holding_sets_sub_asset_class_from_fund_facts(monkeypatch):
    # Sub-class targets (#9543, #9653) bucket by this field.
    gilt = {
        "name": "SPDR Bloomberg 15+ Year Gilt UCITS ETF",
        "instrumentType": "ETF",
        "asset_class": "bond",
        "fund_facts": {"effective_duration_years": 15.04},
    }
    _patch_instrument_meta(monkeypatch, {"GLTL.L": gilt, "VWRL.L": _LEGACY_ETF_META})
    assert enrich_holding({"ticker": "GLTL.L", "units": 0}, date.today(), {}, {})["sub_asset_class"] == "long_gilts"
    # Equity without a small-cap value tilt is broad equity (#9653).
    assert enrich_holding({"ticker": "VWRL.L", "units": 0}, date.today(), {}, {})["sub_asset_class"] == "broad_equity"
