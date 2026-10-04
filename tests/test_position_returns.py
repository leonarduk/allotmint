"""Per-position total return: capital gain plus income and realised gains (#9038)."""

import json
from unittest.mock import patch

import pytest

from backend.common import group_portfolio
from backend.common import portfolio as owner_portfolio
from backend.common.account_models import OwnerSummaryRecord
from backend.common.constants import ACCOUNTS, HOLDINGS
from backend.common.portfolio import add_total_returns
from backend.common.position_returns import TOTAL_RETURN_FIELDS, apply_total_return, position_returns
from backend.config import config

TXS = [
    {"date": "2022-01-10", "ticker": "KO.N", "type": "BUY", "units": 10.0, "price_gbp": 50.0},
    {"date": "2022-06-01", "ticker": "KO.N", "type": "DIVIDEND", "amount_minor": 1200},
    {"date": "2022-09-01", "ticker": "KO.N", "type": "DIVIDENDS", "amount_minor": 800},
    {"date": "2023-01-10", "ticker": "KO.N", "type": "SELL", "units": 4.0, "price_gbp": 60.0},
    {"date": "2022-02-01", "ticker": "IGLT.L", "type": "BUY", "units": 5.0, "price_gbp": 100.0},
    {"date": "2022-08-01", "ticker": "IGLT.L", "type": "INTEREST", "amount_minor": 350},
    # Cash interest belongs to no position.
    {"date": "2022-08-01", "type": "INTEREST", "amount_minor": 999},
    {"date": "2022-08-02", "ticker": "CASH.GBP", "type": "INTEREST", "amount_minor": 111},
]


def _write_transactions(root, owner, account, txs):
    owner_dir = root / owner
    owner_dir.mkdir(exist_ok=True)
    (owner_dir / f"{account}_transactions.json").write_text(json.dumps({"transactions": txs}))


def test_position_returns_sums_income_and_realised_gain_per_instrument():
    returns = position_returns(TXS)
    assert set(returns) == {"KO.N", "IGLT.L"}
    ko = returns["KO.N"]
    assert ko.income_gbp == pytest.approx(20.0)
    # 4 of 10 units at 50 cost 200; sold at 60 for 240.
    assert ko.disposed_cost_gbp == pytest.approx(200.0)
    assert ko.realised_gain_gbp == pytest.approx(40.0)
    assert ko.realised_known
    assert returns["IGLT.L"].income_gbp == pytest.approx(3.5)


def test_total_return_combines_capital_realised_and_income():
    # 6 units left, cost 300, now worth 330.
    holding = {"ticker": "KO.N", "market_value_gbp": 330.0, "gain_gbp": 30.0}
    apply_total_return(holding, position_returns(TXS)["KO.N"])
    assert holding["income_gbp"] == 20.0
    assert holding["realised_gain_gbp"] == 40.0
    assert holding["total_return_gbp"] == 90.0
    # Invested: 300 still held + 200 sold.
    assert holding["total_return_pct"] == pytest.approx(18.0)


def test_unknown_capital_gain_leaves_total_unknown_but_reports_income():
    holding = {"ticker": "KO.N", "market_value_gbp": 330.0, "gain_gbp": None}
    apply_total_return(holding, position_returns(TXS)["KO.N"])
    assert holding["income_gbp"] == 20.0
    assert holding["total_return_gbp"] is None
    assert holding["total_return_pct"] is None


def test_disposal_of_unknown_cost_units_makes_total_unknown():
    txs = [
        {"date": "2021-01-01", "ticker": "ADM.L", "type": "TRANSFER_IN", "units": 10.0},
        {"date": "2022-01-01", "ticker": "ADM.L", "type": "SELL", "units": 2.0, "price_gbp": 30.0},
        {"date": "2022-02-01", "ticker": "ADM.L", "type": "DIVIDEND", "amount_minor": 500},
    ]
    holding = {"ticker": "ADM.L", "market_value_gbp": 300.0, "gain_gbp": 50.0}
    apply_total_return(holding, position_returns(txs)["ADM.L"])
    assert holding["income_gbp"] == 5.0
    assert holding["realised_gain_gbp"] is None
    assert holding["total_return_gbp"] is None


def test_position_with_no_income_or_sales_returns_capital_gain():
    holding = {"ticker": "VWRL.L", "market_value_gbp": 120.0, "gain_gbp": 20.0}
    apply_total_return(holding, None)
    assert holding["income_gbp"] == 0.0
    assert holding["realised_gain_gbp"] == 0.0
    assert holding["total_return_gbp"] == 20.0
    assert holding["total_return_pct"] == pytest.approx(20.0)


def test_ticker_less_dividend_joins_its_pool_by_name():
    txs = [
        {
            "date": "2022-01-10",
            "ticker": "SMT.L",
            "instrument_name": "Scottish Mortgage",
            "type": "BUY",
            "units": 10.0,
            "price_gbp": 10.0,
        },
        {"date": "2022-06-01", "instrument_name": "Scottish Mortgage", "type": "DIVIDEND", "amount_minor": 250},
    ]
    assert position_returns(txs)["SMT.L"].income_gbp == pytest.approx(2.5)


def test_add_total_returns_matches_held_tickers_and_skips_cash(tmp_path):
    _write_transactions(tmp_path, "steve", "ISA", TXS)
    holdings = [
        {"ticker": "KO.N", "market_value_gbp": 330.0, "gain_gbp": 30.0},
        # Suffix-less held ticker still finds its pool, as for derived costs.
        {"ticker": "IGLT", "market_value_gbp": 510.0, "gain_gbp": 10.0},
        {"ticker": "CASH.GBP", "market_value_gbp": 100.0, "gain_gbp": 0.0},
    ]
    add_total_returns("steve", "isa", holdings, tmp_path)
    assert holdings[0]["total_return_gbp"] == 90.0
    assert holdings[1]["income_gbp"] == 3.5
    assert holdings[1]["total_return_gbp"] == 13.5
    assert "income_gbp" not in holdings[2]


def test_ticker_less_position_is_unknown_not_cash(tmp_path):
    _write_transactions(tmp_path, "steve", "ISA", TXS)
    holdings = [{"ticker": "", "name": "Mystery Fund", "market_value_gbp": 10.0, "gain_gbp": 1.0}]
    add_total_returns("steve", "isa", holdings, tmp_path)
    assert all(holdings[0][key] is None for key in TOTAL_RETURN_FIELDS)


def test_add_total_returns_without_transactions_file_reports_unknown(tmp_path):
    (tmp_path / "steve").mkdir()
    holdings = [{"ticker": "KO.N", "market_value_gbp": 330.0, "gain_gbp": 30.0}]
    add_total_returns("steve", "isa", holdings, tmp_path)
    assert holdings[0]["income_gbp"] is None
    assert holdings[0]["total_return_gbp"] is None


def test_group_portfolio_gets_same_total_return_as_owner_portfolio(tmp_path, monkeypatch):
    """The group view locates transactions by ``account_type`` and matches the owner view."""
    owner_dir = tmp_path / "steve"
    owner_dir.mkdir()
    (owner_dir / "ISA_transactions.json").write_text(json.dumps({"transactions": TXS}))
    account = {
        "owner": "steve",
        "account_type": "ISA",
        "currency": "GBP",
        HOLDINGS: [{"ticker": "KO.N", "units": 6.0, "cost_basis_gbp": 300.0}],
    }
    (owner_dir / "isa.json").write_text(json.dumps(account))
    monkeypatch.setattr(config, "accounts_root", tmp_path)

    def priced(h, *_args, **_kwargs):  # isolate from pricing: 6 units now worth 330
        return {**h, "market_value_gbp": 330.0, "gain_gbp": 30.0}

    plots = [OwnerSummaryRecord(owner="steve", accounts=["isa"])]
    with (
        patch("backend.common.portfolio.list_plots", return_value=plots),
        patch("backend.common.portfolio.enrich_holding", side_effect=priced),
    ):
        owner_pf = owner_portfolio.build_owner_portfolio("steve", tmp_path)

    portfolios = [{"owner": "steve", ACCOUNTS: [account]}]
    with (
        patch("backend.common.portfolio_loader.list_portfolios", return_value=portfolios),
        patch("backend.common.group_portfolio.data_loader.list_plots", return_value=plots),
        patch("backend.common.group_portfolio.load_approvals", return_value={}),
        patch("backend.common.group_portfolio.load_user_config", return_value={}),
        patch("backend.common.group_portfolio.enrich_holding", side_effect=priced),
        patch.object(group_portfolio.owner_portfolio, "build_owner_portfolio", return_value={}),
    ):
        group_pf = group_portfolio.build_group_portfolio("all")

    owner_holding = owner_pf[ACCOUNTS][0][HOLDINGS][0]
    group_holding = group_pf[ACCOUNTS][0][HOLDINGS][0]
    assert group_holding["total_return_gbp"] == 90.0
    for key in TOTAL_RETURN_FIELDS:
        assert group_holding[key] == owner_holding[key]
