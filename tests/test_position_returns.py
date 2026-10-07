"""Per-position total return: capital gain plus income and realised gains (#9038)."""

import json
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from backend.common import estimated_income, group_portfolio
from backend.common import portfolio as owner_portfolio
from backend.common import position_returns as position_returns_module
from backend.common.account_models import OwnerSummaryRecord
from backend.common.constants import ACCOUNTS, HOLDINGS
from backend.common.portfolio import add_total_returns
from backend.common.position_returns import (
    TOTAL_RETURN_FIELDS,
    apply_total_return,
    attach_total_returns,
    position_returns,
)
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


# ── Estimated income from dividend history (#10351) ──

HL_TXS = [
    {"date": "2025-05-23", "ticker": "REC.L", "type": "BUY", "units": 5000.0, "price_gbp": 0.5},
    {"date": "2025-09-01", "ticker": "REC.L", "type": "BUY", "units": 1000.0, "price_gbp": 0.5},
    # HL sweeps income into one untagged row: it belongs to no position.
    {"date": "2025-08-10", "type": "DIVIDEND", "amount_minor": 48028, "comments": "Transfer from Income Account"},
]


def _dividends(*pairs):
    return pd.Series([v for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs]))


def _loader(series):
    return lambda symbol, exchange: series if (symbol, exchange) == ("REC", "L") else None


def _attach(holding, txs, series):
    attach_total_returns([holding], txs, lambda ticker, keys: ticker if ticker in keys else None, _loader(series))
    return holding


class _FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 7)


@pytest.fixture
def gbx(monkeypatch):
    monkeypatch.setattr(estimated_income, "_default_currency", lambda symbol, exchange: "GBX")


def test_untagged_dividends_are_estimated_from_history(gbx):
    # 2.5p on 5000 units, then (after the second buy) 2.15p on 6000 units.
    series = _dividends(("2025-07-03", 2.5), ("2025-11-20", 2.15), ("2099-01-01", 9.0))
    holding = _attach({"ticker": "REC.L", "market_value_gbp": 2400.0, "gain_gbp": -600.0}, HL_TXS, series)
    assert holding["income_gbp"] == pytest.approx(125.0 + 129.0)
    assert holding["income_estimated"] is True
    assert holding["total_return_gbp"] == pytest.approx(-600.0 + 254.0)


def test_estimate_uses_the_callers_as_of(gbx):
    series = _dividends(("2025-07-03", 2.5), ("2025-11-20", 2.15))
    holding = {"ticker": "REC.L", "market_value_gbp": 2400.0, "gain_gbp": -600.0}
    attach_total_returns([holding], HL_TXS, lambda ticker, keys: ticker, _loader(series), as_of=date(2025, 8, 1))
    # Only the July ex-date is on or before 2025-08-01, and it is in the trailing year.
    assert holding["income_gbp"] == pytest.approx(125.0)
    assert holding["yield_pct"] == pytest.approx(125.0 / 2400.0 * 100.0)


def test_estimated_income_feeds_the_trailing_yield(gbx, monkeypatch):
    monkeypatch.setattr(position_returns_module, "date", _FixedDate)
    series = _dividends(("2025-07-03", 2.5), ("2025-11-20", 2.15))
    holding = _attach({"ticker": "REC.L", "market_value_gbp": 2400.0, "gain_gbp": -600.0}, HL_TXS, series)
    # Only the November ex-date is in the year to 2026-10-07: 2.15p x 6000 = £129.
    assert holding["yield_pct"] == pytest.approx(129.0 / 2400.0 * 100.0)


def test_units_bought_on_the_ex_date_get_no_dividend(gbx):
    txs = [{"date": "2025-07-03", "ticker": "REC.L", "type": "BUY", "units": 100.0, "price_gbp": 0.5}]
    holding = _attach(
        {"ticker": "REC.L", "market_value_gbp": 50.0, "gain_gbp": 0.0}, txs, _dividends(("2025-07-03", 2.5))
    )
    assert holding["income_gbp"] == 0.0
    assert holding["income_estimated"] is False


def test_units_sold_before_the_ex_date_get_no_dividend(gbx):
    txs = [
        {"date": "2025-01-01", "ticker": "REC.L", "type": "BUY", "units": 100.0, "price_gbp": 0.5},
        {"date": "2025-03-01", "ticker": "REC.L", "type": "SELL", "units": 40.0, "price_gbp": 0.5},
    ]
    holding = _attach(
        {"ticker": "REC.L", "market_value_gbp": 30.0, "gain_gbp": 0.0}, txs, _dividends(("2025-07-03", 2.5))
    )
    assert holding["income_gbp"] == pytest.approx(1.5)


def test_estimate_does_not_depend_on_transaction_order(gbx):
    series = _dividends(("2025-07-03", 2.5), ("2025-11-20", 2.15))
    holding = {"ticker": "REC.L", "market_value_gbp": 2400.0, "gain_gbp": -600.0}
    in_order = _attach(dict(holding), HL_TXS, series)["income_gbp"]
    reversed_ = _attach(dict(holding), list(reversed(HL_TXS)), series)["income_gbp"]
    assert reversed_ == in_order == pytest.approx(254.0)


def test_holding_without_an_entry_reports_income_not_estimated():
    holding = {"ticker": "VWRL.L", "market_value_gbp": 120.0, "gain_gbp": 20.0}
    apply_total_return(holding, None)
    assert holding["income_estimated"] is False


def test_tagged_income_rows_win_over_the_estimate(gbx):
    txs = [*HL_TXS, {"date": "2025-07-20", "ticker": "REC.L", "type": "DIVIDEND", "amount_minor": 12000}]
    holding = _attach(
        {"ticker": "REC.L", "market_value_gbp": 2400.0, "gain_gbp": -600.0}, txs, _dividends(("2025-07-03", 2.5))
    )
    assert holding["income_gbp"] == 120.0
    assert holding["income_estimated"] is False


def test_unknown_dividend_history_keeps_ledger_income(gbx):
    holding = _attach({"ticker": "REC.L", "market_value_gbp": 2400.0, "gain_gbp": -600.0}, HL_TXS, None)
    assert holding["income_gbp"] == 0.0
    assert holding["income_estimated"] is False


def test_estimate_in_pounds_is_not_scaled():
    changes = [("2024-01-01", 10.0)]
    series = _dividends(("2024-06-01", 0.5))
    income = estimated_income.estimated_income_gbp(
        "KO.N", changes, load_dividends=lambda s, e: series, currency_of=lambda s, e: "GBP"
    )
    assert income == estimated_income.IncomeEstimate(pytest.approx(5.0), pytest.approx(5.0))


def test_trailing_window_excludes_its_start_date():
    changes = [("2024-01-01", 10.0)]
    series = _dividends(("2025-01-01", 1.0), ("2025-01-02", 2.0))
    estimate = estimated_income.estimated_income_gbp(
        "KO.N",
        changes,
        load_dividends=lambda s, e: series,
        currency_of=lambda s, e: "GBP",
        today=date(2025, 12, 31),
        trailing_since=date(2025, 1, 1),
    )
    assert estimate.total_gbp == pytest.approx(30.0)
    # Like position_returns' window, the start date itself is outside it.
    assert estimate.trailing_gbp == pytest.approx(20.0)


def test_transfers_move_the_units_entitled_to_a_dividend(gbx):
    txs = [
        {"date": "2024-01-01", "ticker": "REC.L", "type": "TRANSFER_IN", "units": 1000.0},
        {"date": "2024-03-01", "ticker": "REC.L", "type": "TRANSFER_OUT", "units": 400.0},
    ]
    series = _dividends(("2024-02-01", 2.0), ("2024-04-01", 2.0))
    holding = _attach({"ticker": "REC.L", "market_value_gbp": 300.0, "gain_gbp": None}, txs, series)
    # 2p on 1000 units, then 2p on the 600 left after the transfer out.
    assert holding["income_gbp"] == pytest.approx(20.0 + 12.0)
    assert holding["income_estimated"] is True


def test_tagged_income_keeps_its_own_trailing_yield(gbx, monkeypatch):
    monkeypatch.setattr(position_returns_module, "date", _FixedDate)
    txs = [*HL_TXS, {"date": "2026-08-01", "ticker": "REC.L", "type": "DIVIDEND", "amount_minor": 6000}]
    series = _dividends(("2025-11-20", 2.15), ("2026-07-02", 1.45))
    holding = _attach({"ticker": "REC.L", "market_value_gbp": 2400.0, "gain_gbp": -600.0}, txs, series)
    # The recorded £60 drives both income and yield; the estimate is not used.
    assert holding["income_gbp"] == 60.0
    assert holding["income_estimated"] is False
    assert holding["yield_pct"] == pytest.approx(60.0 / 2400.0 * 100.0)


def test_estimate_with_unreadable_currency_metadata_is_unknown():
    def unreadable(symbol, exchange):
        raise OSError("metadata unreadable")

    result = estimated_income.estimated_income_gbp(
        "KO.N",
        [("2024-01-01", 10.0)],
        load_dividends=lambda s, e: _dividends(("2024-06-01", 0.5)),
        currency_of=unreadable,
    )
    assert result is None


def test_add_total_returns_estimates_with_the_stored_history(tmp_path, gbx, monkeypatch):
    """The portfolio path (add_total_returns) reaches the default dividend loader."""
    series = _dividends(("2025-07-03", 2.5))
    monkeypatch.setattr(estimated_income, "_default_loader", _loader(series))
    _write_transactions(tmp_path, "steve", "ISA", HL_TXS)
    holdings = [{"ticker": "REC.L", "market_value_gbp": 2400.0, "gain_gbp": -600.0}]
    add_total_returns("steve", "isa", holdings, tmp_path)
    assert holdings[0]["income_gbp"] == pytest.approx(125.0)
    assert holdings[0]["income_estimated"] is True
    assert holdings[0]["total_return_gbp"] == pytest.approx(-475.0)


def test_estimate_without_fx_rate_is_unknown(monkeypatch):
    def no_rate(value, *args, **kwargs):
        raise ValueError("No FX rate for USD->GBP")

    monkeypatch.setattr(estimated_income.CurrencyNormaliser, "to_gbp", no_rate)
    result = estimated_income.estimated_income_gbp(
        "KO.N",
        [("2024-01-01", 10.0)],
        load_dividends=lambda s, e: _dividends(("2024-06-01", 0.5)),
        currency_of=lambda s, e: "USD",
    )
    assert result is None


def test_trailing_income_counts_only_the_last_twelve_months():
    returns = position_returns(TXS, as_of=date(2023, 3, 1))
    # 2022-06-01 (£12) and 2022-09-01 (£8) fall inside the year to 2023-03-01.
    assert returns["KO.N"].trailing_income_gbp == pytest.approx(20.0)
    later = position_returns(TXS, as_of=date(2023, 7, 1))
    # The June payout has dropped out of the window by July 2023.
    assert later["KO.N"].trailing_income_gbp == pytest.approx(8.0)
    assert later["KO.N"].income_gbp == pytest.approx(20.0)


def test_yield_pct_is_trailing_income_over_market_value():
    holding = {"ticker": "KO.N", "market_value_gbp": 400.0, "gain_gbp": 100.0}
    apply_total_return(holding, position_returns(TXS, as_of=date(2023, 3, 1))["KO.N"])
    assert holding["yield_pct"] == pytest.approx(5.0)


def test_yield_pct_unknown_without_recent_income():
    holding = {"ticker": "KO.N", "market_value_gbp": 400.0, "gain_gbp": 100.0}
    # Nothing paid in the year to 2025: no known yield, not a 0% one.
    apply_total_return(holding, position_returns(TXS, as_of=date(2025, 1, 1))["KO.N"])
    assert holding["yield_pct"] is None
    apply_total_return(holding, None)
    assert holding["yield_pct"] is None


def test_yield_pct_unknown_without_market_value():
    holding = {"ticker": "KO.N", "market_value_gbp": None, "gain_gbp": None}
    apply_total_return(holding, position_returns(TXS, as_of=date(2023, 3, 1))["KO.N"])
    assert holding["yield_pct"] is None
