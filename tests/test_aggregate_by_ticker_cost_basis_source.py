import pytest

from backend.common import portfolio_utils


def _portfolio(*holdings):
    return {"accounts": [{"holdings": list(holdings)}]}


def _holding(ticker, source, owner="a"):
    return {
        "ticker": ticker,
        "owner": owner,
        "units": 1,
        "market_value_gbp": 100,
        "cost_gbp": 100,
        "gain_gbp": 0,
        "cost_basis_source": source,
    }


def _rows(portfolio):
    return {r["ticker"]: r for r in portfolio_utils.aggregate_by_ticker(portfolio)}


def test_row_is_unknown_when_any_contributing_holding_is_unknown():
    rows = _rows(_portfolio(_holding("AAA.L", "book"), _holding("AAA.L", "unknown", owner="b")))
    assert rows["AAA.L"]["cost_basis_source"] == "unknown"


def test_row_is_not_flagged_when_all_holdings_have_a_known_cost():
    rows = _rows(_portfolio(_holding("BBB.L", "book"), _holding("CCC.L", "derived")))
    assert rows["BBB.L"]["cost_basis_source"] is None
    assert rows["CCC.L"]["cost_basis_source"] is None


def test_private_flag_does_not_leak_into_rows():
    rows = _rows(_portfolio(_holding("AAA.L", "unknown"), _holding("DDD.L", "book_suspect")))
    assert "_cost_unknown" not in rows["AAA.L"]
    assert "_cost_suspect" not in rows["DDD.L"]


def _suspect_holding(owner="b"):
    # AV. from #8472: 50 units booked at £263 but worth £33,620; enrich_holding
    # nulls the gain and tags the holding book_suspect.
    return {
        "ticker": "AV.L",
        "owner": owner,
        "units": 50,
        "market_value_gbp": 33620,
        "cost_basis_gbp": 263,
        "effective_cost_basis_gbp": 263,
        "gain_gbp": None,
        "gain_pct": None,
        "cost_basis_source": "book_suspect",
    }


def test_book_suspect_row_is_tagged_and_contributes_no_gain():
    rows = _rows(_portfolio(_suspect_holding()))
    row = rows["AV.L"]
    assert row["cost_basis_source"] == "book_suspect"
    # The suspect £263 is excluded (not replaced by a fabricated cost), so
    # there is no cost to compute a gain from -- not +12,679%.
    assert row["market_value_gbp"] == 33620
    assert row["cost_gbp"] == 0
    assert row["gain_gbp"] == 0
    assert row["gain_pct"] is None
    assert "_suspect_units" not in row


def test_book_suspect_holding_does_not_inflate_a_mixed_row():
    plausible = {
        "ticker": "AV.L",
        "owner": "a",
        "units": 10,
        "market_value_gbp": 6724,
        "cost_basis_gbp": 5000,
        "effective_cost_basis_gbp": 5000,
        "gain_gbp": 1724,
        "cost_basis_source": "book",
    }
    rows = _rows(_portfolio(plausible, _suspect_holding()))
    row = rows["AV.L"]
    assert row["cost_basis_source"] == "book_suspect"
    # cost/gain cover only the plausible holding; market covers both.
    assert row["gain_gbp"] == 1724
    assert row["cost_gbp"] == 5000
    assert row["market_value_gbp"] == 6724 + 33620


def test_book_suspect_units_excluded_from_snapshot_gain_recompute(monkeypatch):
    """With a price snapshot, the row's gain is recomputed from price * units;
    only the units cost_gbp covers may be used, else the suspect holding's
    full market value would be counted as gain."""
    monkeypatch.setattr(
        portfolio_utils,
        "_PRICE_SNAPSHOT",
        {"AV.L": {"last_price": 700.0, "price_currency": "GBP"}},
    )
    plausible = {
        "ticker": "AV.L",
        "owner": "a",
        "units": 10,
        "market_value_gbp": 6724,
        "cost_basis_gbp": 5000,
        "effective_cost_basis_gbp": 5000,
        "gain_gbp": 1724,
        "current_price_gbp": 672.4,
        "cost_basis_source": "book",
    }
    rows = _rows(_portfolio(plausible, _suspect_holding()))
    row = rows["AV.L"]
    assert row["market_value_gbp"] == 60 * 700.0
    assert row["gain_gbp"] == 10 * 700.0 - 5000
    assert row["gain_pct"] == (10 * 700.0 - 5000) / 5000 * 100


def test_book_suspect_takes_precedence_over_unknown_on_a_row():
    rows = _rows(_portfolio(_holding("AV.L", "unknown", owner="a"), _suspect_holding()))
    assert rows["AV.L"]["cost_basis_source"] == "book_suspect"


# ── Sector/region aggregates (#8488) ────────────────────────────────────────


def _lot(ticker, market_value, cost, source, sector="Tech", region="Europe", units=10, owner="a"):
    return {
        "ticker": ticker,
        "owner": owner,
        "units": units,
        "sector": sector,
        "region": region,
        "market_value_gbp": market_value,
        "cost_gbp": cost,
        "gain_gbp": market_value - cost,
        "cost_basis_source": source,
    }


def _by(rows, field):
    return {r[field]: r for r in rows}


def test_sector_gain_pct_ignores_unknown_cost_holding():
    portfolio = _portfolio(
        _lot("ZQA.L", 1200, 1000, "book"),
        # Guessed cost == market value (#7785): would read as 0% at full cost.
        _lot("ZQB.L", 1000, 1000, "unknown"),
    )
    tech = _by(portfolio_utils.aggregate_by_sector(portfolio), "sector")["Tech"]
    assert tech["gain_pct"] == pytest.approx(20.0)
    assert tech["cost_gbp"] == pytest.approx(1000)
    assert tech["gain_gbp"] == pytest.approx(200)
    assert tech["market_value_gbp"] == pytest.approx(2200)
    assert tech["unknown_cost_market_value_gbp"] == pytest.approx(1000)


def test_region_gain_pct_ignores_unknown_cost_holding():
    portfolio = _portfolio(_lot("ZQA.L", 1200, 1000, "book"), _lot("ZQB.L", 1000, 1000, "unknown"))
    europe = _by(portfolio_utils.aggregate_by_region(portfolio), "region")["Europe"]
    assert europe["gain_pct"] == pytest.approx(20.0)
    assert europe["unknown_cost_market_value_gbp"] == pytest.approx(1000)


def test_contribution_pct_excludes_unreliable_cost_and_weights_are_unchanged():
    portfolio = _portfolio(
        _lot("ZQA.L", 1200, 1000, "book"),
        _lot("ZQB.L", 1000, 1000, "unknown"),
        _lot("ZQC.L", 550, 500, "book", sector="Energy"),
    )
    groups = _by(portfolio_utils.aggregate_by_sector(portfolio), "sector")
    reliable_total_cost = 1000 + 500
    assert groups["Tech"]["contribution_pct"] == pytest.approx(200 / reliable_total_cost * 100)
    assert groups["Energy"]["contribution_pct"] == pytest.approx(50 / reliable_total_cost * 100)
    # Market value and weight still include the unknown-cost holding.
    assert groups["Tech"]["market_value_gbp"] == pytest.approx(2200)
    assert groups["Tech"]["weight_pct"] == pytest.approx(2200 / 2750 * 100)
    assert groups["Energy"]["weight_pct"] == pytest.approx(550 / 2750 * 100)


def test_all_reliable_groups_match_plain_sums_of_ticker_rows():
    portfolio = _portfolio(
        _lot("ZQA.L", 1200, 1000, "book"),
        _lot("ZQD.L", 800, 900, "derived"),
        _lot("ZQC.L", 550, 500, None, sector="Energy"),
    )
    rows = portfolio_utils.aggregate_by_ticker(portfolio)
    groups = _by(portfolio_utils.aggregate_by_sector(portfolio), "sector")
    total_cost = sum(r["cost_gbp"] for r in rows)
    for sector, group in groups.items():
        members = [r for r in rows if r["sector"] == sector]
        gain = sum(r["gain_gbp"] for r in members)
        cost = sum(r["cost_gbp"] for r in members)
        assert group["gain_gbp"] == gain
        assert group["cost_gbp"] == cost
        assert group["gain_pct"] == gain / cost * 100.0
        assert group["contribution_pct"] == gain / total_cost * 100.0
        assert group["unknown_cost_market_value_gbp"] == 0.0


def test_book_suspect_holding_excluded_from_sector_gain():
    suspect = dict(_suspect_holding(), sector="Tech", region="Europe")
    portfolio = _portfolio(_lot("ZQA.L", 1200, 1000, "book"), suspect)
    tech = _by(portfolio_utils.aggregate_by_sector(portfolio), "sector")["Tech"]
    assert tech["gain_pct"] == pytest.approx(20.0)
    assert tech["cost_gbp"] == pytest.approx(1000)
    assert tech["market_value_gbp"] == pytest.approx(1200 + 33620)
    assert tech["unknown_cost_market_value_gbp"] == pytest.approx(33620)


def test_mixed_ticker_keeps_reliable_lots_in_sector_figures():
    # One ticker held as a known-cost lot (+20%) and a guessed-cost lot: the
    # ticker row is tagged "unknown" but only the guessed lot is dropped.
    portfolio = _portfolio(
        _lot("ZQA.L", 1200, 1000, "book"),
        _lot("ZQA.L", 1200, 1200, "unknown", owner="b"),
    )
    assert _rows(portfolio)["ZQA.L"]["cost_basis_source"] == "unknown"
    tech = _by(portfolio_utils.aggregate_by_sector(portfolio), "sector")["Tech"]
    assert tech["cost_gbp"] == pytest.approx(1000)
    assert tech["gain_gbp"] == pytest.approx(200)
    assert tech["gain_pct"] == pytest.approx(20.0)
    assert tech["market_value_gbp"] == pytest.approx(2400)
    assert tech["unknown_cost_market_value_gbp"] == pytest.approx(1200)


def test_mixed_ticker_split_uses_snapshot_price(monkeypatch):
    monkeypatch.setattr(
        portfolio_utils,
        "_PRICE_SNAPSHOT",
        {"ZQA.L": {"last_price": 150.0, "price_currency": "GBP"}},
    )
    suspect = dict(_lot("ZQA.L", 1000, 10, "book_suspect", owner="c"), gain_gbp=None)
    portfolio = _portfolio(
        _lot("ZQA.L", 1200, 1000, "book"),
        _lot("ZQA.L", 1200, 1200, "unknown", owner="b"),
        suspect,
    )
    tech = _by(portfolio_utils.aggregate_by_sector(portfolio), "sector")["Tech"]
    # 30 units at the snapshot price of 150; only the book lot's 10 units are costed.
    assert tech["market_value_gbp"] == pytest.approx(4500)
    assert tech["cost_gbp"] == pytest.approx(1000)
    assert tech["gain_gbp"] == pytest.approx(10 * 150 - 1000)
    assert tech["gain_pct"] == pytest.approx(50.0)
    assert tech["unknown_cost_market_value_gbp"] == pytest.approx(20 * 150)


def test_cost_split_does_not_leak_into_ticker_rows():
    rows = _rows(_portfolio(_lot("ZQA.L", 1200, 1000, "book"), _lot("ZQB.L", 1000, 1000, "unknown")))
    for row in rows.values():
        assert "_unreliable_cost_split" not in row
        assert "_unreliable_lots" not in row
