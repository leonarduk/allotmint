"""Unit tests for the Pydantic models in ``backend.routes.portfolio``.

The route module defines a handful of response models that previously had no
direct tests.  These checks exercise their default values to guard against
regressions when the models are extended and to ensure the ``Field``
definitions behave as expected (for example returning fresh lists for each
instance via ``default_factory``).
"""

from backend.routes import portfolio


def test_owner_summary_defaults() -> None:
    """Ensure optional OwnerSummary attributes default sensibly."""

    summary = portfolio.OwnerSummary(
        owner="alex",
        full_name="Alex Example",
        accounts=["ISA", "GIA"],
    )

    assert summary.owner == "alex"
    assert summary.full_name == "Alex Example"
    assert summary.accounts == ["ISA", "GIA"]
    # Optional fields should assume the documented defaults when omitted.
    assert summary.email is None
    assert summary.has_transactions_artifact is False


def test_group_summary_members_default_factory() -> None:
    """Members list should be independent for each GroupSummary instance."""

    first = portfolio.GroupSummary(slug="growth", name="Growth Club")
    second = portfolio.GroupSummary(slug="income", name="Income Club")

    first.members.append("alex")

    assert first.members == ["alex"]
    # ``default_factory`` should ensure a fresh list per model instance.
    assert second.members == []


def test_mover_optional_fields_default_to_none() -> None:
    """Movers expose optional pricing metadata that should default to None."""

    mover = portfolio.Mover(ticker="AAPL.US", name="Apple", change_pct=1.5)

    assert mover.ticker == "AAPL.US"
    assert mover.name == "Apple"
    assert mover.change_pct == 1.5
    assert mover.last_price_gbp is None
    assert mover.last_price_date is None
    assert mover.market_value_gbp is None


def test_movers_response_lists_are_isolated() -> None:
    """MoversResponse gainers/losers lists should not share mutable defaults."""

    response = portfolio.MoversResponse()
    response.gainers.append(
        portfolio.Mover(ticker="AAPL.US", name="Apple", change_pct=2.0)
    )

    another = portfolio.MoversResponse()

    assert response.gainers and response.gainers[0].ticker == "AAPL.US"
    assert another.gainers == []
    assert another.losers == []
