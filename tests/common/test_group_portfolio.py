import time
from unittest.mock import patch

from backend.common import group_portfolio
from backend.common.account_models import OwnerSummaryRecord
from backend.common.constants import ACCOUNTS, HOLDINGS, OWNER


def test_list_groups_returns_expected_defaults():
    owner_rows = [
        OwnerSummaryRecord(owner="Lucy"),
        OwnerSummaryRecord(owner="Steve"),
        OwnerSummaryRecord(owner="Alex"),
        OwnerSummaryRecord(owner="Joe"),
    ]
    with patch("backend.common.group_portfolio.data_loader.list_plots", return_value=owner_rows):
        groups = group_portfolio.list_groups()

    assert groups == [
        {
            "slug": "all",
            "name": "At a glance",
            "members": ["Alex", "Joe", "Lucy", "Steve"],
        },
        {"slug": "adults", "name": "Adults", "members": ["Lucy", "Steve"]},
        {"slug": "children", "name": "Children", "members": ["Alex", "Joe"]},
    ]


def test_list_groups_does_not_load_portfolio_contents():
    """Group discovery must not issue one data load per owner or account."""
    owner_rows = [OwnerSummaryRecord(owner=f"owner-{index}", accounts=[f"account-{index}"]) for index in range(1_000)]

    started_at = time.perf_counter()
    with (
        patch("backend.common.group_portfolio.data_loader.list_plots", return_value=owner_rows),
        patch("backend.common.portfolio_loader.list_portfolios") as list_portfolios,
    ):
        groups = group_portfolio.list_groups()
    elapsed = time.perf_counter() - started_at

    list_portfolios.assert_not_called()
    assert len(groups[0]["members"]) == len(owner_rows)
    assert elapsed < 2


def test_list_groups_excludes_demo_link_owner():
    """The shareable demo-link owner (#7402) must never appear in a real
    user's group view -- see #7676, where "buffett" (config.demo_link_owner)
    was showing up alongside real family members in the "all" group."""
    owner_rows = [
        OwnerSummaryRecord(owner="Lucy"),
        OwnerSummaryRecord(owner="Steve"),
        OwnerSummaryRecord(owner="buffett"),
    ]
    with (
        patch("backend.common.group_portfolio.data_loader.list_plots", return_value=owner_rows),
        patch("backend.common.group_portfolio.config.demo_link_owner", "buffett"),
    ):
        groups = group_portfolio.list_groups()

    all_group = next(g for g in groups if g["slug"] == "all")
    assert "buffett" not in all_group["members"]
    assert all_group["members"] == ["Lucy", "Steve"]


def test_group_members_returns_slug_members():
    owner_rows = [
        OwnerSummaryRecord(owner="Lucy"),
        OwnerSummaryRecord(owner="Steve"),
        OwnerSummaryRecord(owner="Alex"),
        OwnerSummaryRecord(owner="Joe"),
    ]
    with patch("backend.common.group_portfolio.data_loader.list_plots", return_value=owner_rows):
        assert group_portfolio.group_members("adults") == ["Lucy", "Steve"]
        assert group_portfolio.group_members("all") == ["Alex", "Joe", "Lucy", "Steve"]


def test_group_members_unknown_slug_raises_value_error():
    owner_rows = [OwnerSummaryRecord(owner="Lucy")]
    with patch("backend.common.group_portfolio.data_loader.list_plots", return_value=owner_rows):
        try:
            group_portfolio.group_members("does-not-exist")
        except ValueError as exc:
            assert "does-not-exist" in str(exc)
        else:
            raise AssertionError("expected ValueError for unknown group slug")


def test_build_group_portfolio_merges_accounts_and_totals():
    mock_portfolios = [
        {
            "owner": "Lucy",
            ACCOUNTS: [
                {
                    "currency": " usd ",
                    HOLDINGS: [
                        {"ticker": "AAA", "market_value_gbp": 100.0},
                        {"ticker": "BBB", "market_value_gbp": 50.0},
                    ],
                }
            ],
        },
        {
            "owner": "Steve",
            ACCOUNTS: [
                {
                    "currency": None,
                    HOLDINGS: [
                        {"ticker": "CCC", "market_value_gbp": 200.0},
                    ],
                }
            ],
        },
        {"owner": "Alex"},  # present to ensure list_groups builds 'children'
    ]

    patches = [
        patch("backend.common.portfolio_loader.list_portfolios", return_value=mock_portfolios),
        patch(
            "backend.common.group_portfolio.data_loader.list_plots",
            return_value=[OwnerSummaryRecord(owner=row["owner"]) for row in mock_portfolios],
        ),
        patch("backend.common.group_portfolio.load_approvals", return_value={}),
        patch("backend.common.group_portfolio.load_user_config", return_value={}),
        patch(
            "backend.common.group_portfolio.enrich_holding",
            side_effect=lambda h, *_args, **_kwargs: h,
        ),
    ]
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = group_portfolio.build_group_portfolio("adults")

    assert result["slug"] == "adults"
    assert result["members"] == ["Lucy", "Steve"]
    assert len(result[ACCOUNTS]) == 2

    first, second = result[ACCOUNTS]
    assert first[OWNER] == "Lucy"
    assert first["currency"] == "USD"
    assert first["value_estimate_gbp"] == 150.0
    assert second[OWNER] == "Steve"
    assert second["currency"] == "GBP"
    assert second["value_estimate_gbp"] == 200.0

    assert result["total_value_estimate_gbp"] == 350.0
