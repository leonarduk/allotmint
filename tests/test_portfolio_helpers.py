import pytest

from backend.routes import portfolio


def test_calculate_weights_and_market_values():
    summaries = [
        {"ticker": "aaa", "market_value_gbp": 100.0},
        {"ticker": "BBB.L", "market_value_gbp": 50.0},
        {"ticker": None, "market_value_gbp": 10.0},
    ]
    tickers, weights, market_values = portfolio._calculate_weights_and_market_values(summaries)

    # tickers are normalised to uppercase by _calculate_weights_and_market_values
    assert tickers == ["AAA", "BBB.L"]
    assert weights == {"AAA": pytest.approx(50.0), "BBB.L": pytest.approx(50.0)}
    assert market_values["AAA"] == 100.0
    assert market_values["BBB"] == 50.0
    assert market_values["BBB.L"] == 50.0


def test_enrich_movers_with_market_values():
    movers = {
        "gainers": [{"ticker": "AAA"}, {"ticker": "BBB.L"}],
        "losers": [{"ticker": "CCC"}],
    }
    market_values = {"AAA": 100.0, "BBB": 50.0, "BBB.L": 50.0, "CCC": 25.0}
    enriched = portfolio._enrich_movers_with_market_values(movers, market_values)

    assert enriched["gainers"][0]["market_value_gbp"] == 100.0
    assert enriched["gainers"][1]["market_value_gbp"] == 50.0
    assert enriched["losers"][0]["market_value_gbp"] == 25.0


def test_concentration_insight_weights_reflect_aggregated_duplicates():
    """
    Regression for #2702: when a ticker appears across multiple accounts,
    its combined market value must produce a correct percentage weight.

    Pre-fix, the last-write-wins overwrite meant AAA's market_value was 50
    instead of 150, giving a weight of 50/200 = 25% — below a 30% min_weight
    threshold and incorrectly filtered out.

    Post-fix, AAA accumulates to 150, giving 150/200 = 75% — correctly above
    any reasonable concentration threshold.
    """
    summaries = [
        # AAA held in two accounts — should sum to 150
        {"ticker": "AAA", "market_value_gbp": 100.0},
        {"ticker": "AAA", "market_value_gbp": 50.0},
        # BBB held once
        {"ticker": "BBB", "market_value_gbp": 50.0},
    ]
    tickers, weights, market_values = portfolio._calculate_weights_and_market_values(summaries)

    assert tickers == ["AAA", "BBB"]
    # equal-weight fallback (the route recalculates from total_mv — this tests
    # the helper contract, not the route's proportional recalculation)
    assert weights["AAA"] == pytest.approx(50.0)
    assert weights["BBB"] == pytest.approx(50.0)

    # The key regression assertion: market_values must reflect the sum, not
    # just the last-seen value.  75% of portfolio is AAA; 25% is BBB.
    total = market_values["AAA"] + market_values["BBB"]
    aaa_pct = market_values["AAA"] / total * 100.0
    bbb_pct = market_values["BBB"] / total * 100.0

    # With correct aggregation AAA is 75%, well above a 30% concentration threshold.
    assert aaa_pct == pytest.approx(75.0), (
        "AAA weight should be 75% after aggregating duplicate entries; "
        f"got {aaa_pct:.1f}% — duplicate accumulation may be broken"
    )
    assert bbb_pct == pytest.approx(25.0)

    # Explicitly verify the raw aggregated value
    assert market_values["AAA"] == pytest.approx(150.0), (
        "market_values['AAA'] should be 100+50=150; "
        f"got {market_values['AAA']} — last-write-wins regression"
    )
