"""PRICE_SCALE_SUSPECT / LARGE_DAILY_MOVE detection (#7789, #8602).

Motivating cases: AV.L / CLIG.L / HICL.L quoted in pence but read as pounds
(~100x too high), and ADM.L's ``0.1`` scaling override that produced a 10x
discontinuity (#8597, PR #8598).
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.data_quality import issues as issues_module
from backend.data_quality import price_scale
from backend.data_quality.issues import IssueType, aggregate_series_issues


def _frame(closes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Date": dates.strftime("%Y-%m-%d"), "Close": closes})


def _closes(values: list[float]) -> pd.Series:
    return price_scale.close_series(_frame(values))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(issues_module, "_refresh_universe", lambda: [])
    monkeypatch.setattr(issues_module, "_split_dates", lambda t, e: frozenset())


def _run(monkeypatch, closes, meta, *, scale=1.0, ticker="AV", exchange="L", **kwargs):
    df = _frame(closes)
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [(ticker, exchange)])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x", **meta})
    monkeypatch.setattr(issues_module, "get_scaling_override", lambda t, e, r: scale)
    return aggregate_series_issues(**kwargs)


def _of_type(issues, issue_type):
    return [i for i in issues if i.type == issue_type]


@pytest.mark.parametrize(
    ("ticker", "price", "meta"),
    [
        ("AV", 726.0, {"instrumentType": "EQUITY", "currency": "GBP"}),
        ("CLIG", 495.0, {"instrumentType": "Equity", "currency": "GBP"}),
        ("HICL", 134.4, {"instrument_type": "Investment Trust", "currency": "GBP"}),
    ],
)
def test_pence_read_as_pounds_is_flagged_with_override_fix(monkeypatch, ticker, price, meta):
    issues = _run(monkeypatch, [price] * 40, meta, ticker=ticker)

    [issue] = _of_type(issues, IssueType.PRICE_SCALE_SUSPECT)
    assert issue.severity == "high"
    assert issue.fixable is False
    assert "data/scaling_overrides.json" in issue.suggested_fix
    assert f'"{ticker}": 0.01' in issue.suggested_fix
    assert issue.preview["before"]["suggested_factor"] == 0.01


@pytest.mark.parametrize(
    ("ticker", "raw", "scale", "meta"),
    [
        # Correctly converted GBX holdings (raw pence x 0.01).
        ("ULVR", 4633.0, 0.01, {"instrumentType": "Equity", "currency": "GBX"}),
        ("AZN", 12428.0, 0.01, {"instrumentType": "Equity", "currency": "GBX"}),
        ("GAW", 17760.0, 0.01, {"instrumentType": "Equity", "currency": "GBX"}),
        ("FLTR", 20770.0, 0.01, {"instrumentType": "Equity", "currency": "GBX"}),
        ("HICL", 134.4, 0.01, {"instrumentType": "Investment Trust", "currency": "GBX"}),
        # GBP-quoted LSE ETFs legitimately trade at ~GBP 100-300.
        ("ERNS", 100.6, 1.0, {"instrumentType": "ETF", "currency": "GBP"}),
        ("VWRL", 139.0, 1.0, {"instrumentType": "ETF", "currency": "GBP"}),
        ("CUKS", 279.5, 1.0, {"instrumentType": "ETF", "currency": "GBX"}),
    ],
)
def test_correctly_priced_instruments_are_not_flagged(monkeypatch, ticker, raw, scale, meta):
    closes = [raw * (1 + 0.01 * (i % 3)) for i in range(40)]
    issues = _run(monkeypatch, closes, meta, scale=scale, ticker=ticker)

    assert _of_type(issues, IssueType.PRICE_SCALE_SUSPECT) == []
    assert _of_type(issues, IssueType.LARGE_DAILY_MOVE) == []


def test_price_ceiling_ignores_non_lse_exchanges(monkeypatch):
    issues = _run(monkeypatch, [900.0] * 40, {"instrumentType": "Equity"}, ticker="MSFT", exchange="N")
    assert _of_type(issues, IssueType.PRICE_SCALE_SUSPECT) == []


def test_ten_x_step_change_is_flagged(monkeypatch):
    """ADM.L's 0.1 override showed as a ~10x discontinuity (#8597)."""
    closes = [35.88, 35.9, 36.1, 358.8, 359.0]
    issues = _run(monkeypatch, closes, {}, ticker="ADM")

    [issue] = _of_type(issues, IssueType.PRICE_SCALE_SUSPECT)
    [step] = issue.preview["before"]["scale_steps"]
    assert step["previous"] == 36.1 and step["value"] == 358.8
    assert "scaling_overrides.json" not in issue.suggested_fix
    # A scale step is not double-reported as a large daily move.
    assert _of_type(issues, IssueType.LARGE_DAILY_MOVE) == []


def test_latest_close_far_from_trailing_median_is_flagged(monkeypatch):
    # A 30x tick is not a power of ten, so only the median check catches it.
    closes = [10.0] * 35 + [300.0]
    issues = _run(monkeypatch, closes, {})

    [issue] = _of_type(issues, IssueType.PRICE_SCALE_SUSPECT)
    assert issue.preview["before"]["trailing_median_ratio"] == 30.0


def test_normal_moves_raise_nothing(monkeypatch):
    closes = [100.0, 103.0, 98.0, 125.0, 95.0, 101.0]  # mixed-source scale +/-25%
    issues = _run(monkeypatch, closes, {})

    assert _of_type(issues, IssueType.PRICE_SCALE_SUSPECT) == []
    assert _of_type(issues, IssueType.LARGE_DAILY_MOVE) == []


def test_large_daily_move_threshold_boundary_and_configurability(monkeypatch):
    # +50% exactly is not over the default threshold; +60% is.
    assert price_scale.find_large_moves(_closes([100.0, 150.0])) == []
    [move] = price_scale.find_large_moves(_closes([100.0, 160.0]))
    assert move["ratio"] == pytest.approx(1.6)

    issues = _run(monkeypatch, [100.0, 100.0, 40.0], {})
    [issue] = _of_type(issues, IssueType.LARGE_DAILY_MOVE)
    assert issue.severity == "low"

    looser = _run(monkeypatch, [100.0, 100.0, 40.0], {}, large_move_threshold=0.7)
    assert _of_type(looser, IssueType.LARGE_DAILY_MOVE) == []


def test_recorded_split_dates_are_excluded(monkeypatch):
    closes = [100.0, 100.0, 10.0, 10.0]
    split_day = _closes(closes).index[2]
    monkeypatch.setattr(issues_module, "_split_dates", lambda t, e: frozenset({split_day}))

    issues = _run(monkeypatch, closes, {})
    assert _of_type(issues, IssueType.PRICE_SCALE_SUSPECT) == []


def test_close_series_drops_bad_rows_and_duplicate_dates():
    df = pd.DataFrame(
        {
            "Date": ["2026-01-02", "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-05"],
            "Close": [5.0, 4.0, 6.0, 0.0, "x"],
        }
    )
    closes = price_scale.close_series(df)
    assert list(closes.index) == ["2026-01-01", "2026-01-02"]
    assert list(closes) == [4.0, 6.0]


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(10.0, True), (0.01, True), (115.0, True), (1.0, False), (5.0, False), (30.0, False), (0.0, False)],
)
def test_is_scale_step(ratio, expected):
    assert price_scale.is_scale_step(ratio) is expected


@pytest.mark.parametrize(("scale", "expected"), [(1.0, 0.01), (100.0, 1.0), (0.01, None)])
def test_suggested_override_factor(scale, expected):
    assert price_scale.suggested_override_factor(scale) == expected
