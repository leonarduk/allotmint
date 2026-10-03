import copy
import json
import logging
from unittest.mock import patch

from backend.common import group_portfolio
from backend.common import portfolio as owner_portfolio
from backend.common.account_models import OwnerSummaryRecord
from backend.common.constants import ACCOUNTS, HOLDINGS
from backend.common.holdings_rebuild import transaction_cost_hints
from backend.common.portfolio import fill_missing_costs
from backend.config import config

TXS = [
    {"date": "2021-09-26", "ticker": "ADM.L", "type": "TRANSFER_IN", "units": 73.0},
    {"date": "2022-01-10", "ticker": "ADM.L", "type": "BUY", "units": 5.0, "price_gbp": 20.0},
    {"date": "2022-02-01", "ticker": "KO.N", "type": "BUY", "units": 3.0, "price_gbp": 50.0},
    {"date": "2021-09-26", "ticker": "GONE.L", "type": "TRANSFER_IN", "units": 4.0},
    {"date": "2022-03-01", "ticker": "GONE.L", "type": "SELL", "units": 4.0, "price_gbp": 9.0},
]


def _write_transactions(root, owner, account, txs):
    owner_dir = root / owner
    owner_dir.mkdir(exist_ok=True)
    (owner_dir / f"{account}_transactions.json").write_text(json.dumps({"transactions": txs}))
    return owner_dir


def test_cost_hints_cover_only_held_positions():
    hints = transaction_cost_hints(TXS)
    assert hints["ADM.L"] == (None, "2021-09-26")
    assert hints["KO.N"] == (150.0, None)
    assert "GONE.L" not in hints


def test_fill_dates_zero_cost_holdings_from_transfer_in(tmp_path):
    _write_transactions(tmp_path, "steve", "SIPP", TXS)
    holdings = [
        {"ticker": "ADM.L", "units": 78.0, "cost_basis_gbp": 0.0},
        {"ticker": "KO.N", "units": 3.0, "cost_basis_gbp": 150.0},
        {"ticker": "ADM.L", "units": 1.0, "cost_basis_gbp": 0.0, "acquired_date": "2020-01-01"},
        {"ticker": "KO.N", "units": 3.0, "cost_basis_gbp": 0.0},
    ]
    fill_missing_costs("steve", "sipp", holdings, tmp_path)
    assert holdings[0]["acquired_date"] == "2021-09-26"
    assert "acquired_date" not in holdings[1]
    assert holdings[1]["cost_basis_gbp"] == 150.0
    assert holdings[2]["acquired_date"] == "2020-01-01"
    assert holdings[3]["cost_basis_gbp"] == 150.0
    assert "acquired_date" not in holdings[3]


def test_fill_is_a_noop_without_a_transactions_file(tmp_path):
    (tmp_path / "steve").mkdir()
    holdings = [{"ticker": "ADM.L", "units": 1.0, "cost_basis_gbp": 0.0}]
    fill_missing_costs("steve", "isa", holdings, tmp_path)
    assert "acquired_date" not in holdings[0]


def test_dated_zero_cost_holding_uses_fully_known_pool_cost(tmp_path):
    """A placeholder ``acquired_date`` no longer hides an exact transaction cost (#8473)."""
    _write_transactions(tmp_path, "steve", "SIPP", TXS)
    holdings = [{"ticker": "KO.N", "units": 3.0, "cost_basis_gbp": 0.0, "acquired_date": "2020-01-01"}]
    fill_missing_costs("steve", "sipp", holdings, tmp_path)
    assert holdings[0]["cost_basis_gbp"] == 150.0
    assert holdings[0]["acquired_date"] == "2020-01-01"


def test_booked_non_zero_cost_is_never_overwritten(tmp_path):
    _write_transactions(tmp_path, "steve", "SIPP", TXS)
    holdings = [
        {"ticker": "KO.N", "units": 3.0, "cost_basis_gbp": 99.0},
        {"ticker": "KO.N", "units": 3.0, "cost_basis_gbp": 99.0, "acquired_date": "2020-01-01"},
    ]
    fill_missing_costs("steve", "sipp", holdings, tmp_path)
    assert [h["cost_basis_gbp"] for h in holdings] == [99.0, 99.0]
    assert "acquired_date" not in holdings[0]


def test_ticker_differing_only_by_exchange_suffix_matches(tmp_path):
    txs = [
        {"date": "2022-01-10", "ticker": "VWRL.L", "type": "BUY", "units": 10.0, "price_gbp": 100.0},
        {"date": "2022-01-10", "ticker": "ERNS", "type": "BUY", "units": 2.0, "price_gbp": 50.0},
    ]
    _write_transactions(tmp_path, "alex", "ISA", txs)
    holdings = [
        {"ticker": "VWRL", "units": 10.0, "cost_basis_gbp": 0.0},
        {"ticker": "ERNS.L", "units": 2.0, "cost_basis_gbp": 0.0},
    ]
    fill_missing_costs("alex", "isa", holdings, tmp_path)
    assert holdings[0]["cost_basis_gbp"] == 1000.0
    assert holdings[1]["cost_basis_gbp"] == 100.0


def test_ambiguous_base_symbol_is_not_matched(tmp_path, caplog):
    txs = [
        {"date": "2022-01-10", "ticker": "VOD.L", "type": "BUY", "units": 10.0, "price_gbp": 1.0},
        {"date": "2022-01-10", "ticker": "VOD.N", "type": "BUY", "units": 5.0, "price_gbp": 10.0},
        {"date": "2022-01-10", "ticker": "BP", "type": "BUY", "units": 4.0, "price_gbp": 5.0},
    ]
    _write_transactions(tmp_path, "alex", "ISA", txs)
    holdings = [
        # Two pools share the base symbol VOD: no guess.
        {"ticker": "VOD", "units": 10.0, "cost_basis_gbp": 0.0},
        # Two holdings share the base symbol BP: no guess for either.
        {"ticker": "BP.L", "units": 4.0, "cost_basis_gbp": 0.0},
        {"ticker": "BP.N", "units": 4.0, "cost_basis_gbp": 0.0},
    ]
    owner_portfolio._UNMATCHED_COST_WARNED.clear()
    with caplog.at_level(logging.WARNING, logger="backend.common.portfolio"):
        fill_missing_costs("alex", "isa", holdings, tmp_path)
        fill_missing_costs("alex", "isa", copy.deepcopy(holdings), tmp_path)
    assert [h["cost_basis_gbp"] for h in holdings] == [0.0, 0.0, 0.0]
    unmatched = [r for r in caplog.records if "No transaction history matches" in r.getMessage()]
    # One warning per unmatched ticker, not one per request.
    assert len(unmatched) == 3


def test_group_portfolio_gets_same_derived_cost_as_owner_portfolio(tmp_path, monkeypatch):
    """Group views fill zero-cost holdings from transactions exactly like owner views (#8473)."""
    owner_dir = _write_transactions(tmp_path, "steve", "SIPP", TXS)
    account = {
        "owner": "steve",
        "account_type": "SIPP",
        "currency": "GBP",
        HOLDINGS: [
            {"ticker": "KO.N", "units": 3.0, "cost_basis_gbp": 0.0},
            {"ticker": "ADM.L", "units": 78.0, "cost_basis_gbp": 0.0},
        ],
    }
    (owner_dir / "sipp.json").write_text(json.dumps(account))
    monkeypatch.setattr(config, "accounts_root", tmp_path)

    def identity(h, *_args, **_kwargs):  # isolate the cost fill from pricing
        return dict(h)

    plots = [OwnerSummaryRecord(owner="steve", accounts=["sipp"])]
    with (
        patch("backend.common.portfolio.list_plots", return_value=plots),
        patch("backend.common.portfolio.enrich_holding", side_effect=identity),
    ):
        owner_pf = owner_portfolio.build_owner_portfolio("steve", tmp_path)

    portfolios = [{"owner": "steve", ACCOUNTS: [copy.deepcopy(account)]}]
    before = copy.deepcopy(portfolios)
    with (
        patch("backend.common.portfolio_loader.list_portfolios", return_value=portfolios),
        patch("backend.common.group_portfolio.data_loader.list_plots", return_value=plots),
        patch("backend.common.group_portfolio.load_approvals", return_value={}),
        patch("backend.common.group_portfolio.load_user_config", return_value={}),
        patch("backend.common.group_portfolio.enrich_holding", side_effect=identity),
        patch.object(group_portfolio.owner_portfolio, "build_owner_portfolio", return_value={}),
    ):
        group_pf = group_portfolio.build_group_portfolio("all")

    owner_holdings = owner_pf[ACCOUNTS][0][HOLDINGS]
    group_holdings = group_pf[ACCOUNTS][0][HOLDINGS]
    assert group_holdings[0]["cost_basis_gbp"] == 150.0
    assert group_holdings[1]["acquired_date"] == "2021-09-26"
    for key in ("cost_basis_gbp", "acquired_date"):
        assert [h.get(key) for h in group_holdings] == [h.get(key) for h in owner_holdings]
    # The list_portfolios() data handed to the group builder is not mutated.
    assert portfolios == before
