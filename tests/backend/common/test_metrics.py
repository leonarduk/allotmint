import datetime as dt
import json

import pytest

from backend.common import metrics


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-03-01", dt.date(2024, 3, 1)),
        (dt.date(2020, 1, 2), dt.date(2020, 1, 2)),
        ("", None),
        (None, None),
        ("not-a-date", None),
    ],
)
def test_parse_date_handles_various_inputs(value, expected):
    assert metrics._parse_date(value) == expected


def test_position_periods_tracks_closed_and_open_positions():
    txs = [
        {"date": "2024-01-01", "ticker": "aaa", "type": "Buy", "shares": 5},
        {"date": "2024-01-03", "ticker": "AAA", "type": "purchase", "quantity": 5},
        {"date": "2024-01-10", "ticker": "AAA", "type": "Sell", "shares": 4},
        {"date": "2024-01-15", "ticker": "AAA", "kind": "SELL", "shares": 6},
        {"date": None, "ticker": "CCC", "type": "BUY", "shares": 1},
        {"date": "2024-02-01", "ticker": "bbb", "type": "BUY", "shares": 2},
        {"date": "2024-02-05", "ticker": "BBB", "type": "DIVIDEND", "shares": 1},
    ]

    periods = metrics.position_periods("owner", txs)

    assert periods == [
        metrics.PositionPeriod("AAA", dt.date(2024, 1, 1), dt.date(2024, 1, 15)),
        metrics.PositionPeriod("BBB", dt.date(2024, 2, 1), None),
    ]


def test_position_periods_ignores_incomplete_transactions():
    txs = [
        {"date": "", "ticker": "AAA", "type": "BUY", "shares": 1},
        {"date": "2024-01-01", "ticker": "", "type": "BUY", "shares": 1},
        {"date": "2024-01-02", "ticker": "BBB", "type": "UNKNOWN", "shares": 1},
        {"date": "2024-01-03", "ticker": "CCC", "type": "SELL", "shares": 1},
    ]

    periods = metrics.position_periods("owner", txs)

    # Only the last transaction has usable data, but without a prior buy it shouldn't create a period.
    assert periods == []


def test_calculate_portfolio_turnover_with_zero_portfolio_value():
    txs = [
        {"date": "2024-01-01", "ticker": "AAA", "type": "BUY", "amount_minor": -1000},
    ]

    assert metrics.calculate_portfolio_turnover("owner", txs, portfolio_value=0) == 0.0


def test_calculate_portfolio_turnover_aggregates_trade_amounts():
    txs = [
        {"date": "2024-01-01", "ticker": "AAA", "type": "BUY", "amount_minor": -1000},
        {"date": "2024-01-02", "ticker": "AAA", "type": "SELL", "amount_minor": 1500},
        {"date": "2024-01-03", "ticker": "BBB", "type": "purchase", "amount_minor": 500},
        {"date": "2024-01-04", "ticker": "CCC", "type": "DIVIDEND", "amount_minor": 2000},
    ]

    turnover = metrics.calculate_portfolio_turnover("owner", txs, portfolio_value=200)

    # Only buy/purchase/sell amounts are summed and converted from minor units.
    expected = (abs(-1000) + abs(1500) + abs(500)) / 100 / 200
    assert turnover == expected


def test_calculate_average_holding_period_includes_open_positions():
    txs = [
        {"date": "2024-01-01", "ticker": "AAA", "type": "BUY", "shares": 10},
        {"date": "2024-01-05", "ticker": "AAA", "type": "SELL", "shares": 10},
        {"date": "2024-02-01", "ticker": "BBB", "type": "BUY", "shares": 5},
    ]

    as_of = dt.date(2024, 2, 11)

    avg = metrics.calculate_average_holding_period("owner", txs, as_of=as_of)

    # Periods: AAA held 4 days, BBB open for 10 days -> average 7.0
    expected = ((dt.date(2024, 1, 5) - dt.date(2024, 1, 1)).days + (as_of - dt.date(2024, 2, 1)).days) / 2
    assert avg == expected


def test_compute_and_store_metrics_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(metrics, "METRICS_DIR", tmp_path)

    txs = [
        {"date": "2024-01-01", "ticker": "AAA", "type": "BUY", "shares": 5, "amount_minor": 1000},
        {"date": "2024-01-10", "ticker": "AAA", "type": "SELL", "shares": 5, "amount_minor": 1500},
    ]

    as_of = dt.date(2024, 1, 31)
    metrics_data = metrics.compute_and_store_metrics(
        "owner", txs, as_of=as_of, portfolio_value=100
    )

    metrics_path = tmp_path / "owner_metrics.json"
    assert metrics_path.exists()

    stored = json.loads(metrics_path.read_text())
    assert stored == metrics_data
    assert metrics_data["owner"] == "owner"
    assert metrics_data["as_of"] == as_of.isoformat()
    assert metrics_data["turnover"] == metrics.calculate_portfolio_turnover(
        "owner", txs, portfolio_value=100
    )
    assert metrics_data["average_holding_period"] == metrics.calculate_average_holding_period(
        "owner", txs, as_of=as_of
    )
