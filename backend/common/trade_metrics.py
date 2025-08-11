from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List

TRADE_LOG_PATH = Path(__file__).resolve().parents[2] / "data" / "trade_log.csv"


def load_trades(path: Path = TRADE_LOG_PATH) -> List[Dict[str, str]]:
    """Load trade records from *path*.

    The log is expected to be a CSV file with the columns:
    ``timestamp``, ``ticker``, ``action`` and ``price``.
    """
    if not path.exists():
        return []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def compute_metrics(trades: Iterable[Dict[str, str]]) -> Dict[str, float]:
    """Return win rate and average profit/loss for *trades*.

    ``trades`` should be an iterable of dicts with at least ``ticker``,
    ``action`` and ``price`` keys. BUY prices are paired with the next SELL
    for the same ticker to compute profit/loss.
    """
    positions: Dict[str, float] = {}
    profits: List[float] = []

    for trade in trades:
        ticker = trade["ticker"]
        action = trade["action"].upper()
        price = float(trade["price"])
        if action == "BUY":
            positions[ticker] = price
        elif action == "SELL" and ticker in positions:
            buy_price = positions.pop(ticker)
            profits.append(price - buy_price)

    if not profits:
        return {"win_rate": 0.0, "average_profit": 0.0}

    wins = sum(1 for p in profits if p > 0)
    win_rate = wins / len(profits)
    average_profit = sum(profits) / len(profits)
    return {"win_rate": win_rate, "average_profit": average_profit}


def load_and_compute_metrics(path: Path = TRADE_LOG_PATH) -> Dict[str, float]:
    """Convenience wrapper loading the trade log at *path* and computing metrics."""
    trades = load_trades(path)
    return compute_metrics(trades)
