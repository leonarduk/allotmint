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
