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
    monkeypatch.setattr(issues_module, "invalid_scaling_override", lambda t, e: None)


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
    """A ~10x discontinuity inside the cached series (#8597).

    No override factor is suggested: overrides are applied to the whole series
    at read time, so no factor can remove a step between two of its points.
    ADM.L's actual root cause, an invalid ``0.1`` in scaling_overrides.json,
    is reported with its replacement factor by the invalid-override tests.
    """
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


def test_single_day_move_suspect_flags_ten_x_step(monkeypatch):
    """The ADM.L discontinuity from #8597 / PR #8598 is flagged at refresh time."""
    closes = [35.88, 35.9, 36.1, 358.8]
    issues = _run(monkeypatch, closes, {}, ticker="ADM")

    [issue] = _of_type(issues, IssueType.SINGLE_DAY_MOVE_SUSPECT)
    assert issue.severity == "low"
    assert issue.fixable is False
    assert issue.preview["before"]["move"]["previous"] == 36.1
    assert issue.preview["before"]["move"]["value"] == 358.8


def test_single_day_move_suspect_ignores_normal_moves(monkeypatch):
    issues = _run(monkeypatch, [100.0, 101.0, 99.5, 100.2], {})
    assert _of_type(issues, IssueType.SINGLE_DAY_MOVE_SUSPECT) == []


def test_single_day_move_suspect_threshold_boundary(monkeypatch):
    # Exactly the threshold is not flagged; just over it is.
    assert _of_type(_run(monkeypatch, [100.0, 150.0], {}), IssueType.SINGLE_DAY_MOVE_SUSPECT) == []
    assert len(_of_type(_run(monkeypatch, [100.0, 150.1], {}), IssueType.SINGLE_DAY_MOVE_SUSPECT)) == 1
    # A per-instrument threshold loosens the check for a volatile name.
    assert (
        _of_type(_run(monkeypatch, [100.0, 150.1], {"large_move_threshold": 0.8}), IssueType.SINGLE_DAY_MOVE_SUSPECT)
        == []
    )


def test_single_day_move_suspect_excludes_recorded_splits(monkeypatch):
    closes = [100.0, 100.0, 10.0]
    split_day = _closes(closes).index[2]
    monkeypatch.setattr(issues_module, "_split_dates", lambda t, e: frozenset({split_day}))
    issues = _run(monkeypatch, closes, {})
    assert _of_type(issues, IssueType.SINGLE_DAY_MOVE_SUSPECT) == []


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


# ── Real get_scaling_override, no stub (#7789 review) ───────────────────────
# ``_price_ceiling_reason`` calls ``get_scaling_override(ticker, exchange,
# None)``. ``None`` means "no caller-requested factor", which makes the helper
# resolve the *effective* factor: the scaling_overrides.json entry first, then
# the instrument's currency metadata (GBX -> 0.01). These tests run that real
# resolution against an override table shaped like the demo dataset before the
# companion data fix (no AV/HICL entries, ULVR present), so a correctly
# converted GBX holding cannot be mistaken for a raw pence price.

_REAL_META = {
    "AV.L": {"name": "Aviva", "instrumentType": "Equity", "currency": "GBP"},
    "HICL.L": {"name": "HICL", "instrumentType": "Investment Trust", "currency": "GBP"},
    "ULVR.L": {"name": "Unilever", "instrumentType": "Equity", "currency": "GBP"},
    "GAW.L": {"name": "Games Workshop", "instrumentType": "Equity", "currency": "GBX"},
    "ERNS.L": {"name": "iShares GBP Ultrashort", "instrumentType": "ETF", "currency": "GBP"},
}
_REAL_RAW_CLOSE = {"AV": 726.0, "HICL": 134.4, "ULVR": 4633.0, "GAW": 17760.0, "ERNS": 100.6}


@pytest.fixture
def real_scaling(monkeypatch, tmp_path):
    from backend.common import instruments as instruments_module
    from backend.utils import timeseries_helpers

    overrides = tmp_path / "scaling_overrides.json"
    overrides.write_text('{"L": {"ULVR": 0.01}}', encoding="utf-8")
    monkeypatch.setattr(timeseries_helpers, "_scaling_override_paths", lambda: [overrides])
    monkeypatch.setattr(instruments_module, "get_instrument_meta", lambda full: _REAL_META.get(full, {}))
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda full: _REAL_META.get(full, {}))
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [(t, "L") for t in _REAL_RAW_CLOSE])
    monkeypatch.setattr(
        issues_module,
        "load_cached_meta_timeseries_full",
        lambda t, e: _frame([_REAL_RAW_CLOSE[t]] * 40),
    )


def test_real_scaling_override_flags_only_unconverted_pence(real_scaling):
    issues = _of_type(aggregate_series_issues(), IssueType.PRICE_SCALE_SUSPECT)

    # AV / HICL have neither an override nor GBX metadata: raw pence read as GBP.
    # ULVR (override 0.01) and GAW (GBX metadata) resolve to 0.01 and are fine;
    # ERNS is a GBP ETF and never price-gated.
    by_ticker = {i.entity["ticker"]: i for i in issues}
    assert set(by_ticker) == {"AV", "HICL"}
    assert by_ticker["AV"].preview["before"]["scale"] == 1.0
    assert '"AV": 0.01 under "L"' in by_ticker["AV"].suggested_fix


def test_gbx_currency_metadata_alone_resolves_pence_with_none_requested(real_scaling):
    """``get_scaling_override(t, "L", None)``: None is the *requested* factor, not
    the exchange/currency, so GBX metadata with no override entry still yields 0.01."""
    from backend.utils.timeseries_helpers import get_scaling_override

    assert get_scaling_override("GAW", "L", None) == pytest.approx(0.01)
    issues = _of_type(aggregate_series_issues(), IssueType.PRICE_SCALE_SUSPECT)
    assert "GAW" not in {i.entity["ticker"] for i in issues}  # raw 17760p = £177.60, under the £300 ceiling


# ── _split_dates against the real corporate-actions loader ──────────────────
_real_split_dates = issues_module._split_dates  # captured before _isolate stubs it


def _actions_folder(monkeypatch, tmp_path):
    from backend.timeseries import corporate_actions

    real_loader = corporate_actions.load_corporate_actions
    monkeypatch.setattr(
        issues_module,
        "load_corporate_actions",
        lambda t, e: real_loader(t, e, base=str(tmp_path)),
    )
    folder = tmp_path / corporate_actions.ACTIONS_DIR
    folder.mkdir()
    return folder


def test_split_dates_reads_recorded_splits(monkeypatch, tmp_path):
    folder = _actions_folder(monkeypatch, tmp_path)
    pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-03-01", "2024-06-03"]),
            "Action": ["split", "dividend"],
            "Value": [10.0, 0.5],
            "Currency": ["", "GBP"],
            "Source": ["test", "test"],
        }
    ).to_parquet(folder / "AV_L.parquet")

    assert _real_split_dates("AV", "L") == frozenset({"2024-03-01"})


def test_split_dates_missing_or_unreadable_file_is_empty_not_fatal(monkeypatch, tmp_path):
    folder = _actions_folder(monkeypatch, tmp_path)
    assert _real_split_dates("AV", "L") == frozenset()  # no file at all

    (folder / "AV_L.parquet").write_bytes(b"not a parquet file")
    assert _real_split_dates("AV", "L") == frozenset()  # corrupt file is logged, not raised


# ── Shared real-resolution harness for the tests below ─────────────────────
def _real_env(monkeypatch, tmp_path, *, overrides_json, meta, series):
    """Run aggregate_series_issues with the real get_scaling_override and
    invalid_scaling_override over ``series`` ({ticker: closes}) on "L"."""
    from backend.common import instruments as instruments_module
    from backend.utils import timeseries_helpers

    overrides = tmp_path / "scaling_overrides.json"
    overrides.write_text(overrides_json, encoding="utf-8")
    monkeypatch.setattr(timeseries_helpers, "_scaling_override_paths", lambda: [overrides])
    monkeypatch.setattr(issues_module, "invalid_scaling_override", timeseries_helpers.invalid_scaling_override)
    monkeypatch.setattr(instruments_module, "get_instrument_meta", lambda full: meta.get(full, {}))
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda full: meta.get(full, {}))
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [(t, "L") for t in series])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: _frame(series[t]))
    return _of_type(aggregate_series_issues(), IssueType.PRICE_SCALE_SUSPECT)


# ── ADM.L: an invalid override factor is reported with its replacement ──────
# ADM.L was listed as 0.1 in scaling_overrides.json (#8597). get_scaling_override
# ignores invalid factors, so the entry drifts silently unless the Data Quality
# page reports it. The fix names the file and the valid factor to put there.


@pytest.mark.parametrize(
    ("currency", "expected_price_reason"),
    [
        # GBX metadata: the ignored 0.1 falls back to 0.01, so the price is
        # right but the table entry is still wrong.
        ("GBX", False),
        # GBP metadata: the fallback is 1.0, so raw pence also breach the
        # equity ceiling. Both reasons agree on the replacement factor.
        ("GBP", True),
    ],
)
def test_invalid_adm_override_names_file_and_factor(monkeypatch, tmp_path, currency, expected_price_reason):
    issues = _real_env(
        monkeypatch,
        tmp_path,
        overrides_json='{"L": {"ADM": 0.1}}',
        meta={"ADM.L": {"name": "Admiral", "instrumentType": "Equity", "currency": currency}},
        series={"ADM": [3588.0] * 40},
    )

    [issue] = issues
    assert issue.severity == "high"
    assert issue.fixable is False
    assert issue.preview["before"]["invalid_override"] == 0.1
    assert issue.preview["before"]["suggested_factor"] == 0.01
    assert 'Replace "ADM": 0.1 under "L" in data/scaling_overrides.json with "ADM": 0.01' in issue.suggested_fix
    assert ("plausible for instrument type" in issue.description) is expected_price_reason


def test_valid_override_is_not_reported(monkeypatch, tmp_path):
    issues = _real_env(
        monkeypatch,
        tmp_path,
        overrides_json='{"L": {"ADM": 0.01}}',
        meta={"ADM.L": {"name": "Admiral", "instrumentType": "Equity", "currency": "GBP"}},
        series={"ADM": [3588.0] * 40},
    )
    assert issues == []


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ('{"L": {"ADM": 0.1}}', 0.1),
        ('{"l": {"ADM": 0.1}}', 0.1),  # exchange sections are case-insensitive
        ('{"L": {"ADM": 0.01}}', None),
        ('{"L": {"ADM": 100}}', None),
        ('{"L": {"ADM": "pence"}}', None),
        ('{"L": {"OTHER": 0.1}}', None),
        ('{"*": {"ADM": 0.1}}', None),  # wildcard rows are not a per-instrument finding
        ("{}", None),
    ],
)
def test_invalid_scaling_override(monkeypatch, tmp_path, table, expected):
    from backend.utils import timeseries_helpers

    overrides = tmp_path / "scaling_overrides.json"
    overrides.write_text(table, encoding="utf-8")
    monkeypatch.setattr(timeseries_helpers, "_scaling_override_paths", lambda: [overrides])
    assert timeseries_helpers.invalid_scaling_override("ADM.L", "L") == expected


# ── Issue #7789 AC: the named false-positive candidates ─────────────────────
# Metadata (instrumentType, currency) mirrors allotmint-data/instruments/L/*.json.
# Levels are approximate GBP (ETFs) or pence (GBX equities) prices; the issue
# gives ERNS ~GBP 100, VWRL ~GBP 139, GBPG ~GBP 42 and the GBX holdings' GBP
# values. The override table is empty, so GBX holdings must resolve via metadata.
_AC_ETFS = {
    "ERNS": ("GBP", 100.6),
    "GBPG": ("GBP", 42.0),
    "SEGA": ("GBP", 22.5),
    "VHYL": ("GBP", 62.0),
    "VWRL": ("GBP", 139.0),
    "ISXF": ("GBP", 4.4),
    "WCOS": ("USD", 6.1),
    "GILG": ("GBP", 9.6),
    "AIGE": ("USD", 30.5),
    "ESIH": ("GBP", 7.3),
}
_AC_GBX_HOLDINGS = {"ULVR": 4633.0, "AZN": 12428.0, "III": 2715.0, "GAW": 17760.0}


def _random_walk(end: float, seed: int, days: int = 260, daily_vol: float = 0.012) -> list[float]:
    """A year of business-day closes: lognormal steps, fixed seed, ending at ``end``."""
    import numpy as np

    steps = np.random.default_rng(seed).normal(0.0, daily_vol, days - 1)
    path = np.exp(np.concatenate([[0.0], np.cumsum(steps)]))
    return [float(v) for v in end * path / path[-1]]


@pytest.mark.parametrize(
    ("ticker", "currency", "instrument_type", "level"),
    [(t, c, "ETF", p) for t, (c, p) in _AC_ETFS.items()]
    + [(t, "GBX", "Equity", p) for t, p in _AC_GBX_HOLDINGS.items()],
)
def test_issue_ac_false_positive_candidates_are_not_flagged(
    monkeypatch, tmp_path, ticker, currency, instrument_type, level
):
    issues = _real_env(
        monkeypatch,
        tmp_path,
        overrides_json='{"L": {}}',
        meta={f"{ticker}.L": {"name": ticker, "instrumentType": instrument_type, "currency": currency}},
        series={ticker: _random_walk(level, seed=sum(map(ord, ticker)))},
    )
    assert issues == []
