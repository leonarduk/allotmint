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
    rows = _rows(_portfolio(_holding("AAA.L", "unknown")))
    assert "_cost_unknown" not in rows["AAA.L"]
