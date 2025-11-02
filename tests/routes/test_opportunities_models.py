"""Regression tests for the Opportunities Pydantic models."""

from backend.agent.models import TradingSignal
from backend.routes import opportunities


def test_opportunity_entry_defaults() -> None:
    """Optional pricing metadata and trading signals should default to ``None``."""

    entry = opportunities.OpportunityEntry(
        ticker="AAPL.US",
        name="Apple",
        change_pct=3.2,
        side="gainers",
    )

    assert entry.ticker == "AAPL.US"
    assert entry.name == "Apple"
    assert entry.change_pct == 3.2
    assert entry.side == "gainers"
    assert entry.last_price_gbp is None
    assert entry.last_price_date is None
    assert entry.market_value_gbp is None
    assert entry.signal is None

    signal = TradingSignal(
        ticker="AAPL.US",
        action="BUY",
        reason="Momentum breakout",
        confidence=0.75,
    )

    enriched = opportunities.OpportunityEntry(
        ticker="AAPL.US",
        name="Apple",
        change_pct=3.2,
        side="gainers",
        signal=signal,
    )

    assert enriched.signal is signal


def test_opportunities_context_list_defaults() -> None:
    """List fields should be isolated between OpportunitiesContext instances."""

    first = opportunities.OpportunitiesContext(source="group", group="core", days=7)
    second = opportunities.OpportunitiesContext(source="watchlist", days=1)

    first.tickers.append("MSFT.US")
    first.anomalies.append("delisted")

    assert first.tickers == ["MSFT.US"]
    assert first.anomalies == ["delisted"]
    assert second.tickers == []
    assert second.anomalies == []
    assert second.group is None


def test_opportunities_response_default_factories() -> None:
    """Entries and signals use ``default_factory`` and must not share lists."""

    context = opportunities.OpportunitiesContext(source="group", group="core", days=30)

    response = opportunities.OpportunitiesResponse(context=context)
    response.entries.append(
        opportunities.OpportunityEntry(
            ticker="TSLA.US",
            name="Tesla",
            change_pct=-4.1,
            side="losers",
        )
    )

    another = opportunities.OpportunitiesResponse(
        context=opportunities.OpportunitiesContext(source="watchlist", days=1)
    )

    assert response.entries and response.entries[0].ticker == "TSLA.US"
    assert response.signals == []
    assert another.entries == []
    assert another.signals == []
