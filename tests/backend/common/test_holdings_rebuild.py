"""Tests for rebuilding holdings from transactions without losing data."""

from __future__ import annotations

import logging

import pytest

from backend.common.holdings_rebuild import rebuild_holdings_document, replay_transactions


def _holdings(doc: dict) -> dict[str, dict]:
    return {h["ticker"]: h for h in doc["holdings"]}


def _buy(ticker: str, units: float, pounds: float, day: str, **extra) -> dict:
    return {"type": "BUY", "ticker": ticker, "units": units, "amount_minor": round(pounds * 100), "date": day, **extra}


def _sell(ticker: str, units: float, pounds: float, day: str, **extra) -> dict:
    return {"type": "SELL", "ticker": ticker, "units": units, "amount_minor": round(pounds * 100), "date": day, **extra}


def test_cost_basis_uses_section_104_average_cost() -> None:
    tx = {
        "transactions": [
            _buy("ABC.L", 100, 1_000.00, "2024-01-10"),
            _buy("ABC.L", 100, 2_000.00, "2024-02-10"),
            _sell("ABC.L", 50, 900.00, "2024-03-10"),
        ]
    }

    abc = _holdings(rebuild_holdings_document(tx, "alex", "isa"))["ABC.L"]

    assert abc["units"] == pytest.approx(150)
    # Pool cost 3000 for 200 units; selling 50 removes 750.
    assert abc["cost_basis_gbp"] == pytest.approx(2_250.00)
    assert abc["acquired_date"] == "2024-02-10"


def test_cost_falls_back_to_price_and_fees_without_amount() -> None:
    tx = {
        "transactions": [
            {"type": "BUY", "ticker": "X", "units": 10, "price_gbp": 2.5, "fees": 1.5, "date": "2024-01-01"}
        ]
    }

    assert _holdings(rebuild_holdings_document(tx, "a", "isa"))["X"]["cost_basis_gbp"] == pytest.approx(26.5)


def test_same_day_acquisition_is_pooled_before_disposal() -> None:
    # Listed sell-first, as broker statements often are.
    tx = {"transactions": [_sell("ABC", 10, 120, "2024-01-10"), _buy("ABC", 20, 200, "2024-01-10")]}

    abc = _holdings(rebuild_holdings_document(tx, "a", "isa"))["ABC"]

    assert abc["units"] == pytest.approx(10)
    assert abc["cost_basis_gbp"] == pytest.approx(100)


def test_unchanged_holding_keeps_value_and_extra_fields() -> None:
    tx = {"transactions": [_buy("ABC", 10, 100, "2024-01-10"), _buy("NEW", 5, 50, "2024-02-01")]}
    existing = {
        "owner": "alex",
        "account_type": "ISA",
        "notes": "hand maintained",
        "holdings": [{"ticker": "ABC", "units": 10, "value_gbp": 140.0, "cost_basis_gbp": 99.0, "name": "Abc plc"}],
    }

    doc = rebuild_holdings_document(tx, "alex", "isa", existing)
    holdings = _holdings(doc)

    assert doc["notes"] == "hand maintained"
    assert [h["ticker"] for h in doc["holdings"]] == ["ABC", "NEW"]
    assert holdings["ABC"]["value_gbp"] == 140.0
    assert holdings["ABC"]["name"] == "Abc plc"
    assert holdings["ABC"]["cost_basis_gbp"] == pytest.approx(100.0)  # transactions win when cost is known
    assert "value_gbp" not in holdings["NEW"]


def test_changed_units_revalue_at_last_known_price() -> None:
    tx = {"transactions": [_buy("ABC", 10, 100, "2024-01-10"), _sell("ABC", 4, 60, "2024-03-01")]}
    existing = {"holdings": [{"ticker": "ABC", "units": 10, "value_gbp": 150.0}]}

    abc = _holdings(rebuild_holdings_document(tx, "a", "isa", existing))["ABC"]

    assert abc["units"] == pytest.approx(6)
    assert abc["value_gbp"] == pytest.approx(90.0)


def test_unknown_cost_units_keep_existing_cost_when_units_unchanged() -> None:
    tx = {"transactions": [{"type": "TRANSFER_IN", "ticker": "OLD", "units": 50, "date": "2021-09-26"}]}
    existing = {"holdings": [{"ticker": "OLD", "units": 50, "cost_basis_gbp": 812.34}]}

    old = _holdings(rebuild_holdings_document(tx, "a", "isa", existing))["OLD"]

    assert old["cost_basis_gbp"] == 812.34


def test_unknown_cost_units_with_changed_units_leave_cost_to_be_derived() -> None:
    tx = {
        "transactions": [
            {"type": "TRANSFER_IN", "ticker": "OLD", "units": 50, "date": "2021-09-26"},
            _buy("OLD", 10, 200, "2024-01-01"),
        ]
    }
    existing = {"holdings": [{"ticker": "OLD", "units": 50, "cost_basis_gbp": 812.34}]}

    old = _holdings(rebuild_holdings_document(tx, "a", "isa", existing))["OLD"]

    # 0.0 tells get_effective_cost_basis_gbp to derive it from prices.
    assert old["cost_basis_gbp"] == 0.0


def test_selling_all_unknown_cost_units_makes_later_cost_known() -> None:
    tx = {
        "transactions": [
            {"type": "TRANSFER_IN", "ticker": "OLD", "units": 50, "date": "2021-09-26"},
            _sell("OLD", 50, 900, "2022-01-01"),
            _buy("OLD", 10, 200, "2024-01-01"),
        ]
    }

    assert _holdings(rebuild_holdings_document(tx, "a", "isa"))["OLD"]["cost_basis_gbp"] == pytest.approx(200)


def test_ticker_less_trades_join_ticker_pool_by_instrument_name() -> None:
    tx = {
        "transactions": [
            _buy("FUND.L", 10, 100, "2024-01-01", instrument_name="Some Fund Acc"),
            {**_buy("", 10, 300, "2024-02-01"), "ticker": None, "instrument_name": "Some Fund Acc"},
        ]
    }

    fund = _holdings(rebuild_holdings_document(tx, "a", "isa"))["FUND.L"]

    assert fund["units"] == pytest.approx(20)
    assert fund["cost_basis_gbp"] == pytest.approx(400)


def test_ticker_less_trades_resolve_through_existing_holding_name() -> None:
    tx = {"transactions": [{"type": "BUY", "instrument_name": "Some Fund Acc", "units": 5, "amount_minor": 5000}]}
    existing = {"holdings": [{"ticker": "FUND.L", "name": "Some Fund Acc", "units": 0}]}

    assert _holdings(rebuild_holdings_document(tx, "a", "isa", existing))["FUND.L"]["units"] == pytest.approx(5)


def test_unresolvable_ticker_less_position_is_left_out(caplog: pytest.LogCaptureFixture) -> None:
    tx = {"transactions": [{"type": "BUY", "instrument_name": "Mystery Fund", "units": 5, "amount_minor": 5000}]}
    caplog.set_level(logging.WARNING, logger="backend.common.holdings_rebuild")

    doc = rebuild_holdings_document(tx, "a", "isa")

    assert doc["holdings"] == []
    assert "No ticker known" in caplog.text


def test_oversold_position_is_not_emitted_negative(caplog: pytest.LogCaptureFixture) -> None:
    tx = {"transactions": [{"type": "SELL", "instrument_name": "Old Fund", "units": 5, "amount_minor": 500}]}
    caplog.set_level(logging.WARNING, logger="backend.common.holdings_rebuild")

    doc = rebuild_holdings_document(tx, "a", "isa")

    assert doc["holdings"] == []
    assert "exceeds units held" in caplog.text


def test_trade_cash_ignored_without_opt_in() -> None:
    tx = {
        "transactions": [
            {"type": "DEPOSIT", "amount_minor": 100_000},
            _buy("ABC", 10, 400, "2024-01-10"),
            {"type": "FEES", "amount_minor": 500},
        ]
    }

    cash = _holdings(rebuild_holdings_document(tx, "a", "isa"))["CASH.GBP"]

    assert cash["units"] == pytest.approx(1_000.0)
    assert cash["cost_basis_gbp"] == pytest.approx(1_000.0)


def test_trade_cash_applied_with_opt_in() -> None:
    tx = {
        "trade_cash_effects": True,
        "transactions": [
            {"type": "TRANSFER_IN", "ticker": "CASH.GBP", "units": 50.0, "date": "2024-01-01"},
            {"type": "DEPOSIT", "amount_minor": 100_000},
            _buy("ABC", 10, 400, "2024-01-10"),
            _sell("ABC", 5, 300, "2024-02-10"),
            {"type": "FEES", "amount_minor": 500},
            {"type": "FEES_REFUND", "amount_minor": 200},
            {"type": "INTEREST_CHARGE", "amount_minor": 100},
            {"type": "INTEREST", "amount_minor": 50},
            {"type": "DIVIDEND", "amount_minor": 1_000},
        ],
    }
    existing = {"holdings": [{"ticker": "CASH.GBP", "units": 1.0, "value_gbp": 1.0, "cost_basis_gbp": 0.01}]}

    cash = _holdings(rebuild_holdings_document(tx, "a", "isa", existing))["CASH.GBP"]

    expected = 50 + 1_000 - 400 + 300 - 5 + 2 - 1 + 0.5 + 10
    assert cash["units"] == pytest.approx(expected)
    assert cash["value_gbp"] == pytest.approx(expected)
    assert cash["cost_basis_gbp"] == pytest.approx(expected)


def test_ticker_less_trades_move_cash_with_opt_in() -> None:
    tx = {
        "trade_cash_effects": True,
        "transactions": [
            {"type": "BUY", "instrument_name": "Fund", "units": 5, "amount_minor": 50_000},
            {"type": "SELL", "instrument_name": "Fund", "units": 5, "amount_minor": 45_000},
        ],
    }

    replay = replay_transactions(tx["transactions"], trade_cash=True)

    assert replay.cash == pytest.approx(-50.0)


def test_sold_out_holding_is_dropped() -> None:
    tx = {"transactions": [_buy("ABC", 10, 100, "2024-01-10"), _sell("ABC", 10, 120, "2024-02-10")]}
    existing = {"holdings": [{"ticker": "ABC", "units": 10, "value_gbp": 120.0}]}

    assert rebuild_holdings_document(tx, "a", "isa", existing)["holdings"] == []


def test_top_level_fields_are_refreshed() -> None:
    existing = {"owner": "stale", "account_type": "old", "currency": "USD", "last_updated": "2000-01-01"}

    doc = rebuild_holdings_document({"transactions": []}, "alex", "isa", existing)

    assert doc["owner"] == "alex"
    assert doc["account_type"] == "ISA"
    assert doc["currency"] == "USD"
    assert doc["last_updated"] != "2000-01-01"
