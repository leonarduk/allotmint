"""Per-instrument large-move thresholds and refresh-time move suspects (#8602).

Motivating case: ADM.L's ``0.1`` scaling override produced a ~10x
discontinuity that nothing flagged; it was found by hand (#8597, PR #8598).
"""

from __future__ import annotations

import logging

import pandas as pd
import pytest

from backend.common import prices
from backend.data_quality import issues as issues_module
from backend.data_quality import price_scale
from backend.data_quality.issues import IssueType, aggregate_series_issues


def _frame(closes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Date": dates, "Close": closes})


def _closes(values: list[float]) -> pd.Series:
    return price_scale.close_series(_frame(values))


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (None, 0.5),
        ({}, 0.5),
        ({"large_move_threshold": 0.8}, 0.8),
        ({"large_move_threshold": "0.3"}, 0.3),
        # Bad values fall back rather than silencing (or flooding) the check.
        ({"large_move_threshold": 0}, 0.5),
        ({"large_move_threshold": -1}, 0.5),
        ({"large_move_threshold": "high"}, 0.5),
        ({"large_move_threshold": float("nan")}, 0.5),
        ({"large_move_threshold": True}, 0.5),
    ],
)
def test_large_move_threshold_reads_instrument_meta(meta, expected):
    assert price_scale.large_move_threshold(meta) == expected


def test_large_move_threshold_uses_caller_default():
    assert price_scale.large_move_threshold({}, 0.2) == 0.2
    assert price_scale.large_move_threshold({"large_move_threshold": 0.9}, 0.2) == 0.9


def test_latest_move_boundary_and_scale_steps():
    # Exactly the threshold is not flagged; just over it is.
    assert price_scale.latest_move(_closes([100.0, 150.0]), 0.5) is None
    step = price_scale.latest_move(_closes([100.0, 150.1]), 0.5)
    assert step is not None and step["ratio"] == pytest.approx(1.501)
    # A 10x step (ADM.L, #8597) is flagged at refresh time.
    step = price_scale.latest_move(_closes([35.9, 36.1, 358.8]), 0.5)
    assert step is not None and step["previous"] == 36.1 and step["value"] == 358.8
    # Only the latest step counts, and short series are ignored.
    assert price_scale.latest_move(_closes([100.0, 10.0, 10.2]), 0.5) is None
    assert price_scale.latest_move(_closes([100.0]), 0.5) is None


def _run_aggregate(monkeypatch, closes, meta, **kwargs):
    df = _frame(closes)
    monkeypatch.setattr(issues_module, "_refresh_universe", lambda: [])
    monkeypatch.setattr(issues_module, "_split_dates", lambda t, e: frozenset())
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [("SMALL", "L")])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x", **meta})
    monkeypatch.setattr(issues_module, "get_scaling_override", lambda t, e, r: 1.0)
    return [i for i in aggregate_series_issues(**kwargs) if i.type == IssueType.LARGE_DAILY_MOVE]


def test_per_instrument_threshold_overrides_global_default(monkeypatch):
    closes = [100.0, 100.0, 40.0]  # -60%
    assert len(_run_aggregate(monkeypatch, closes, {})) == 1
    assert _run_aggregate(monkeypatch, closes, {"large_move_threshold": 0.7}) == []
    # A tighter per-instrument threshold catches a move the default ignores.
    assert len(_run_aggregate(monkeypatch, [100.0, 100.0, 70.0], {"large_move_threshold": 0.2})) == 1
    # The per-instrument value wins over the caller's global value too.
    assert _run_aggregate(monkeypatch, closes, {"large_move_threshold": 0.7}, large_move_threshold=0.1) == []


@pytest.fixture
def _cached(monkeypatch):
    series = {
        "ADM.L": [35.88, 35.9, 36.1, 358.8],  # 10x step from a bad override
        "VOD.L": [100.0, 101.0, 99.5, 100.2],  # normal day
        "SMALL.L": [100.0, 100.0, 40.0],  # -60%, but tuned to 0.7
    }
    metas = {"SMALL.L": {"large_move_threshold": 0.7}}
    monkeypatch.setattr(prices, "load_meta_timeseries", lambda s, e, days: _frame(series[f"{s}.{e}"]))
    monkeypatch.setattr("backend.common.instruments.get_instrument_meta", lambda t: metas.get(t, {}))


def test_refresh_logs_only_suspect_moves(_cached, caplog):
    with caplog.at_level(logging.WARNING, logger=prices.logger.name):
        suspects = prices.log_large_move_suspects(["ADM.L", "VOD.L", "SMALL.L"])

    assert [s["ticker"] for s in suspects] == ["ADM.L"]
    assert suspects[0]["ratio"] == pytest.approx(358.8 / 36.1)
    [record] = [r for r in caplog.records if "Price move suspect" in r.getMessage()]
    assert "ADM.L" in record.getMessage() and "50% threshold" in record.getMessage()


def test_refresh_move_check_failure_is_logged_not_raised(monkeypatch, caplog):
    def boom(*_args):
        raise OSError("cache unreadable")

    monkeypatch.setattr(prices, "load_meta_timeseries", boom)
    with caplog.at_level(logging.WARNING, logger=prices.logger.name):
        assert prices.log_large_move_suspects(["ADM.L"]) == []
    assert any("Large-move check failed for ADM.L" in r.getMessage() for r in caplog.records)


def test_refresh_prices_runs_the_move_check(monkeypatch, tmp_path):
    seen: list[list[str]] = []
    monkeypatch.setattr(prices, "refresh_universe", lambda: ["ADM.L"])
    monkeypatch.setattr(prices, "get_price_snapshot", lambda t: {})
    monkeypatch.setattr(prices, "_refresh_reference_data", lambda t: None)
    monkeypatch.setattr(prices, "log_large_move_suspects", lambda t: seen.append(list(t)) or [])
    monkeypatch.setattr(prices, "check_price_alerts", lambda: None)
    monkeypatch.setattr(prices.price_triggers, "evaluate", lambda _snapshot: None)
    monkeypatch.setattr(prices.config, "prices_json", str(tmp_path / "latest_prices.json"))
    monkeypatch.setattr(prices.config, "app_env", "local")

    prices.refresh_prices()

    assert seen == [["ADM.L"]]
