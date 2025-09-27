from unittest.mock import patch

from backend.common.constants import ACCOUNTS, HOLDINGS, OWNER
from backend.common import group_portfolio


def test_list_groups_returns_expected_defaults():
    mock_portfolios = [
        {"owner": "Lucy"},
        {"owner": "Steve"},
        {"owner": "Alex"},
        {"owner": "Joe"},
    ]
    with patch("backend.common.portfolio_loader.list_portfolios", return_value=mock_portfolios):
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


def test_build_group_portfolio_merges_accounts_and_totals():
    mock_portfolios = [
        {
            "owner": "Lucy",
            ACCOUNTS: [
                {
                    HOLDINGS: [
                        {"ticker": "AAA", "market_value_gbp": 100.0},
                        {"ticker": "BBB", "market_value_gbp": 50.0},
                    ]
                }
            ],
        },
        {
            "owner": "Steve",
            ACCOUNTS: [
                {
                    HOLDINGS: [
                        {"ticker": "CCC", "market_value_gbp": 200.0},
                    ]
                }
            ],
        },
        {"owner": "Alex"},  # present to ensure list_groups builds 'children'
    ]

    patches = [
        patch("backend.common.portfolio_loader.list_portfolios", return_value=mock_portfolios),
        patch("backend.common.group_portfolio.load_approvals", return_value={}),
        patch("backend.common.group_portfolio.load_user_config", return_value={}),
        patch(
            "backend.common.group_portfolio.enrich_holding",
            side_effect=lambda h, *_args, **_kwargs: h,
        ),
    ]
    with patches[0], patches[1], patches[2], patches[3]:
        result = group_portfolio.build_group_portfolio("adults")

    assert result["slug"] == "adults"
    assert result["members"] == ["Lucy", "Steve"]
    assert len(result[ACCOUNTS]) == 2

    first, second = result[ACCOUNTS]
    assert first[OWNER] == "Lucy"
    assert first["value_estimate_gbp"] == 150.0
    assert second[OWNER] == "Steve"
    assert second["value_estimate_gbp"] == 200.0

    assert result["total_value_estimate_gbp"] == 350.0
