"""Look-through exposure across funds and direct holdings (#9974)."""

import pytest

from backend.common import look_through

FUND_BLOCK = {
    "source": "morningstar",
    "as_of": "2026-08-31",
    "countries": {"United States": 60.0, "United Kingdom": 40.0},
    "sectors": {"Information Technology": 50.0, "Financials": 50.0},
    "top_holdings": [
        {"name": "Microsoft Corp", "isin": "US5949181045", "weight_pct": 10.0},
        {"name": "HSBC Holdings", "isin": "GB0005405286", "weight_pct": 5.0},
    ],
    "holdings_count": 1000,
}

META = {
    "WRLD.L": {"name": "World ETF", "instrumentType": "ETF", "isin": "IE00B0000001", "look_through": FUND_BLOCK},
    "MSFT.N": {"name": "Microsoft", "instrumentType": "EQUITY", "isin": "US5949181045"},
    "INFRA.L": {"name": "Infra Trust", "instrumentType": "Investment Trust", "isin": "GB00B0000002"},
    "GOLD.L": {"name": "Physical Gold", "instrumentType": "ETC", "asset_class": "commodity", "isin": "JE00B0000003"},
}


def _rows(*rows):
    return [
        {"ticker": t, "name": META.get(t, {}).get("name", t), "market_value_gbp": v, "sector": s, "region": r}
        for t, v, s, r in rows
    ]


@pytest.fixture
def portfolio(monkeypatch):
    def _set(*rows):
        monkeypatch.setattr(look_through, "aggregate_by_ticker", lambda _p: _rows(*rows))
        return look_through.compute_look_through({"accounts": []})

    monkeypatch.setattr(look_through, "get_instrument_meta", lambda t: META.get(t, {}))
    return _set


def _by_label(buckets):
    return {b["label"]: b["value_gbp"] for b in buckets}


def test_fund_is_split_by_its_country_and_sector_weights(portfolio):
    result = portfolio(("WRLD.L", 1000.0, "Multi-sector", "Europe"))

    assert _by_label(result["countries"]) == {"United States": 600.0, "United Kingdom": 400.0}
    assert _by_label(result["sectors"]) == {"Information Technology": 500.0, "Financials": 500.0}
    assert result["coverage"]["looked_through_value_gbp"] == 1000.0
    assert result["coverage"]["funds"][0]["as_of"] == "2026-08-31"


def test_direct_share_and_fund_holding_combine_by_isin(portfolio):
    result = portfolio(("WRLD.L", 1000.0, "Multi-sector", "Europe"), ("MSFT.N", 200.0, "Technology", "US"))

    msft = next(h for h in result["holdings"] if h["isin"] == "US5949181045")
    assert msft["value_gbp"] == 300.0
    assert msft["direct_value_gbp"] == 200.0
    assert msft["via_funds_value_gbp"] == 100.0
    assert msft["name"] == "Microsoft"
    assert {s["ticker"] for s in msft["sources"]} == {"MSFT.N", "WRLD.L"}
    # The direct share counts to its ISIN country and normalised sector.
    assert _by_label(result["countries"])["United States"] == 800.0
    assert _by_label(result["sectors"])["Information Technology"] == 700.0


def test_unpublished_part_of_fund_is_one_residual_line(portfolio):
    result = portfolio(("WRLD.L", 1000.0, "Multi-sector", "Europe"))

    other = result["holdings"][-1]
    assert other["key"] == look_through.OTHER_FUND_HOLDINGS_KEY
    assert other["value_gbp"] == 850.0
    assert sum(h["value_gbp"] for h in result["holdings"]) == pytest.approx(1000.0)


def test_fund_without_data_keeps_sector_and_is_reported(portfolio):
    result = portfolio(("INFRA.L", 300.0, "Utilities", "United Kingdom"), ("GOLD.L", 50.0, "Commodities", "Jersey"))

    assert _by_label(result["countries"]) == {look_through.NOT_LOOKED_THROUGH: 300.0, "Commodities": 50.0}
    assert _by_label(result["sectors"]) == {"Utilities": 300.0, "Commodities": 50.0}
    assert [f["ticker"] for f in result["coverage"]["not_covered"]] == ["INFRA.L", "GOLD.L"]
    assert result["coverage"]["not_covered_value_gbp"] == 350.0
    infra = next(h for h in result["holdings"] if h["key"] == "GB00B0000002")
    assert infra["kind"] == "fund"


def test_cash_and_totals_reconcile(portfolio):
    result = portfolio(
        ("WRLD.L", 1000.0, "Multi-sector", "Europe"),
        ("MSFT.N", 200.0, "Technology", "US"),
        ("INFRA.L", 300.0, "Utilities", "United Kingdom"),
        ("CASH.GBP", 500.0, "Cash", None),
    )

    total = 2000.0
    assert result["total_value_gbp"] == total
    for key in ("countries", "sectors", "holdings"):
        assert sum(b["value_gbp"] for b in result[key]) == pytest.approx(total), key
    assert sum(b["weight_pct"] for b in result["countries"]) == pytest.approx(100.0)
    assert _by_label(result["countries"])["Cash"] == 500.0
    assert result["coverage"]["cash_value_gbp"] == 500.0
    assert result["coverage"]["direct_value_gbp"] == 200.0


def test_direct_share_without_isin_uses_region_code(portfolio, monkeypatch):
    monkeypatch.setattr(look_through, "get_instrument_meta", lambda t: {"instrumentType": "EQUITY"})
    result = portfolio(("XYZ.N", 100.0, "Energy", "US"))

    assert _by_label(result["countries"]) == {"United States": 100.0}
    assert result["holdings"][0]["key"] == "XYZ.N"


def test_fund_holdings_over_100pct_are_capped(portfolio, monkeypatch):
    block = {**FUND_BLOCK, "top_holdings": [{"name": "A", "isin": None, "weight_pct": 70.0}] * 2}
    monkeypatch.setattr(look_through, "get_instrument_meta", lambda t: {"isin": "IE00B0000001", "look_through": block})
    result = portfolio(("WRLD.L", 1000.0, None, None))

    assert sum(h["value_gbp"] for h in result["holdings"]) == pytest.approx(1000.0)


def test_block_without_weights_is_ignored():
    assert look_through.usable_look_through({"look_through": {"countries": {}, "sectors": {"X": 1}}}) is None
    assert look_through.usable_look_through({"look_through": "bad"}) is None
    assert look_through.usable_look_through({"look_through": FUND_BLOCK}) is FUND_BLOCK


@pytest.fixture
def meta(monkeypatch):
    monkeypatch.setattr(look_through, "get_instrument_meta", lambda t: META.get(t, {}))


@pytest.mark.usefixtures("meta")
def test_instrument_allocation_for_fund_uses_look_through():
    result = look_through.instrument_allocation("WRLD.L")

    assert result["kind"] == "fund"
    assert result["source"] == "morningstar"
    assert result["countries"] == [
        {"label": "United States", "weight_pct": 60.0},
        {"label": "United Kingdom", "weight_pct": 40.0},
    ]
    assert result["top_holdings"][0]["isin"] == "US5949181045"


@pytest.mark.usefixtures("meta")
def test_instrument_allocation_for_single_share_is_itself():
    result = look_through.instrument_allocation("MSFT.N")

    assert result["kind"] == "security"
    assert result["countries"] == [{"label": "United States", "weight_pct": 100.0}]
    assert result["top_holdings"] == [
        {
            "name": "Microsoft",
            "isin": "US5949181045",
            "weight_pct": 100.0,
            "country": "United States",
            "sector": look_through.UNKNOWN_LABEL,
        }
    ]


@pytest.mark.usefixtures("meta")
def test_instrument_allocation_for_uncovered_fund_and_cash():
    infra = look_through.instrument_allocation("INFRA.L")
    gold = look_through.instrument_allocation("GOLD.L")
    cash = look_through.instrument_allocation("CASH.GBP")

    assert infra["kind"] == "fund_uncovered"
    assert infra["countries"] == [{"label": look_through.NOT_LOOKED_THROUGH, "weight_pct": 100.0}]
    assert gold["countries"] == [{"label": look_through.COMMODITIES_COUNTRY, "weight_pct": 100.0}]
    assert cash["kind"] == "cash"
    assert cash["top_holdings"] == []
