"""Group view finds transactions by account file stem, not ``account_type``.

An account file ``isa.json`` whose ``account_type`` is ``Stocks ISA`` keeps its
transactions in ``isa_transactions.json``.  The owner view locates them by the
file stem; the group view used ``account_type`` and silently skipped the
derived cost (#8473) and total return (#9038) for such accounts.
"""

import json
from unittest.mock import patch

from backend.common import group_portfolio
from backend.common import portfolio as owner_portfolio
from backend.common.account_models import OwnerSummaryRecord
from backend.common.constants import ACCOUNTS, HOLDINGS
from backend.common.portfolio_loader import ACCOUNT_STEM_KEY
from backend.common.position_returns import TOTAL_RETURN_FIELDS
from backend.config import config

TXS = [
    {"date": "2022-01-10", "ticker": "KO.N", "type": "BUY", "units": 10.0, "price_gbp": 50.0},
    {"date": "2022-06-01", "ticker": "KO.N", "type": "DIVIDEND", "amount_minor": 1200},
    {"date": "2022-09-01", "ticker": "KO.N", "type": "DIVIDENDS", "amount_minor": 800},
    {"date": "2023-01-10", "ticker": "KO.N", "type": "SELL", "units": 4.0, "price_gbp": 60.0},
]


def _priced(h, *_args, **_kwargs):
    """Isolate from pricing: 6 units now worth 330, gain against whatever cost is set."""
    cost = float(h.get("cost_basis_gbp") or 0.0)
    return {**h, "market_value_gbp": 330.0, "gain_gbp": 330.0 - cost if cost else None}


def test_group_view_uses_file_stem_when_account_type_differs(tmp_path, monkeypatch):
    owner_dir = tmp_path / "steve"
    owner_dir.mkdir()
    (owner_dir / "isa_transactions.json").write_text(json.dumps({"transactions": TXS}))
    account = {
        "owner": "steve",
        "account_type": "Stocks ISA",
        "currency": "GBP",
        # No booked cost: the transactions must supply it.
        HOLDINGS: [{"ticker": "KO.N", "units": 6.0, "cost_basis_gbp": 0.0}],
    }
    (owner_dir / "isa.json").write_text(json.dumps(account))
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    plots = [OwnerSummaryRecord(owner="steve", accounts=["isa"])]

    with (
        patch("backend.common.portfolio.list_plots", return_value=plots),
        patch("backend.common.portfolio.enrich_holding", side_effect=_priced),
    ):
        owner_pf = owner_portfolio.build_owner_portfolio("steve", tmp_path)

    # The real loader runs, so the stem travels from list_plots to the builder.
    with (
        patch("backend.common.portfolio_loader.list_plots", return_value=plots),
        patch("backend.common.portfolio_loader.load_person_meta", return_value={}),
        patch("backend.common.group_portfolio.data_loader.list_plots", return_value=plots),
        patch("backend.common.group_portfolio.load_approvals", return_value={}),
        patch("backend.common.group_portfolio.load_user_config", return_value={}),
        patch("backend.common.group_portfolio.enrich_holding", side_effect=_priced),
        patch.object(group_portfolio.owner_portfolio, "build_owner_portfolio", return_value={}),
    ):
        group_pf = group_portfolio.build_group_portfolio("all")

    owner_holding = owner_pf[ACCOUNTS][0][HOLDINGS][0]
    group_account = group_pf[ACCOUNTS][0]
    group_holding = group_account[HOLDINGS][0]

    assert group_account["account_type"] == "Stocks ISA"
    assert ACCOUNT_STEM_KEY not in group_account
    # Cost fill: 4 of 10 units at 50 sold leaves a pool cost of 300.
    assert group_holding["cost_basis_gbp"] == 300.0
    assert group_holding["cost_basis_gbp"] == owner_holding["cost_basis_gbp"]
    # Total return: 30 capital + 40 realised + 20 income.
    assert group_holding["total_return_gbp"] == 90.0
    for key in TOTAL_RETURN_FIELDS:
        assert group_holding[key] == owner_holding[key]


def test_account_file_name_falls_back_to_account_type_without_stem():
    assert group_portfolio._account_file_name({"account_type": " ISA "}) == "ISA"
    assert group_portfolio._account_file_name({"account_type": "Stocks ISA", ACCOUNT_STEM_KEY: "isa"}) == "isa"
