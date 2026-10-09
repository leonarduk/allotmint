"""Change-of-direction detector for held instruments (#10476). Plain code, no LLM.

A holding is flagged only when **several** trend signals agree *and* at least
one *trigger* signal is **new**: off in each of the last ``memory_runs`` weekly
runs. A single RSI or MACD reading never flags anything on its own, MACD and
swing structure can add agreement but never make a flag new, and a long-standing
loser does not resurface every week. Each signal is a boolean per trading day:

* ``death_cross`` -- the 50-day average is below the 200-day average;
* ``below_falling_sma200`` -- the price is below a 200-day average that is
  lower than it was ``sma_slope_days`` ago;
* ``rs_new_low`` -- relative strength against the benchmark made a new
  ``rs_low_days`` low within the last ``new_lookback_days``;
* ``lower_highs_lows`` -- the latest ``swing_days`` window has both a lower
  high and a lower low than the window before it;
* ``break_52w_low`` -- the price closed below its prior 52-week low within the
  last ``new_lookback_days``;
* ``macd_negative`` -- the MACD line (12/26) is below zero.

The triggers are the first four less ``lower_highs_lows``: the averages, relative
strength and the 52-week low. Choosing them was a backtest call (see
:mod:`backend.trend_watch.backtest`): letting MACD or swing flicker make a flag
new tripled how often holdings were flagged with no better hit rate. At least
one of the price-trend signals (the averages or the 52-week low) must also be
on: relative strength and MACD alone are both moved by a short dip.

The parameters (50/200-day averages, MACD 12/26/9, a 52-week range) are the ones
allotmint-pro's ``get_instrument_technicals`` reports, so the panel and that
tool describe the same chart. The maths is computed here as whole series rather
than imported, because the detector needs every day's reading (to find what is
new, and for the backtest) while the pro tool returns the latest values only,
and because the free backend must run without allotmint-pro installed.

Relative figures are only as good as their basis: callers pass total-return
levels where a dividend history is stored and say which basis each side uses
(``return_basis``, #9370), and that basis is reported with every relative figure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from backend.config import TrendWatchConfig
from backend.data_quality import price_scale
from backend.timeseries.quality import find_gaps

DEATH_CROSS = "death_cross"
BELOW_FALLING_SMA200 = "below_falling_sma200"
RS_NEW_LOW = "rs_new_low"
LOWER_HIGHS_LOWS = "lower_highs_lows"
BREAK_52W_LOW = "break_52w_low"
MACD_NEGATIVE = "macd_negative"
SIGNALS = (DEATH_CROSS, BELOW_FALLING_SMA200, RS_NEW_LOW, LOWER_HIGHS_LOWS, BREAK_52W_LOW, MACD_NEGATIVE)
# Signals whose switching on can make a flag new.
TRIGGER_SIGNALS = frozenset({DEATH_CROSS, BELOW_FALLING_SMA200, RS_NEW_LOW, BREAK_52W_LOW})
# A flag needs at least one of these: the price trend itself has turned.
PRICE_TREND_SIGNALS = frozenset({DEATH_CROSS, BELOW_FALLING_SMA200, BREAK_52W_LOW})

SIGNAL_LABELS = {
    DEATH_CROSS: "50-day average below the 200-day average (death cross)",
    BELOW_FALLING_SMA200: "price below a falling 200-day average",
    RS_NEW_LOW: "relative strength vs its benchmark at a new 6-month low",
    LOWER_HIGHS_LOWS: "lower high and lower low than the previous month",
    BREAK_52W_LOW: "closed below its previous 52-week low",
    MACD_NEGATIVE: "MACD line below zero",
}

SMA_FAST, SMA_SLOW = 50, 200
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
RANGE_DAYS = 252
# Trading days over which the holding's and the benchmark's moves are compared.
MOVE_DAYS = 63
# Only price steps this recent can explain (or fake) a current change of direction.
ARTEFACT_LOOKBACK_DAYS = 260
# Missing closes for longer than this many business days in that window bend the averages.
GAP_ARTEFACT_DAYS = 5


@dataclass
class Detection:
    """The detector's reading of one ticker on one day."""

    ticker: str
    as_of: Optional[str] = None
    active: List[str] = field(default_factory=list)
    new: List[str] = field(default_factory=list)
    flagged: bool = False
    change_score: float = 0.0
    values: Dict[str, Any] = field(default_factory=dict)
    # Price steps that look like data artefacts (a split or a GBX/GBP flip).
    artefacts: List[Dict[str, Any]] = field(default_factory=list)
    reason: Optional[str] = None
    # The active signals of this run and the earlier runs it remembers, newest first.
    recent: List[List[str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def state(self) -> Dict[str, Any]:
        """What the next run needs to tell new signals from old ones."""

        return {"as_of": self.as_of, "active": list(self.active), "recent": self.recent, "rs": self.values.get("rs")}


def clean_series(series: Optional[pd.Series]) -> pd.Series:
    if series is None or series.empty:
        return pd.Series(dtype=float)
    out = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    out = out[out > 0]
    out.index = pd.to_datetime(out.index)
    return out[~out.index.duplicated(keep="last")].sort_index()


def _recent_event(flags: pd.Series, days: int) -> pd.Series:
    """True where ``flags`` fired on that day or within the ``days - 1`` days before it."""

    return flags.astype(float).rolling(max(days, 1), min_periods=1).max().fillna(0).astype(bool)


def signal_frame(
    closes: pd.Series,
    benchmark: Optional[pd.Series] = None,
    cfg: Optional[TrendWatchConfig] = None,
) -> pd.DataFrame:
    """Every day's indicator values and boolean signals for ``closes``.

    ``closes`` are the traded prices (averages, MACD and the range use them).
    ``benchmark`` is the comparison series for relative strength, ideally on
    the same return basis as the instrument; without it ``rs_new_low`` is
    never on. Days without enough history read ``False``, never estimated.
    """

    cfg = cfg or TrendWatchConfig()
    closes = clean_series(closes)
    frame = pd.DataFrame({"close": closes})
    if closes.empty:
        for name in SIGNALS:
            frame[name] = pd.Series(dtype=bool)
        return frame

    frame["sma50"] = closes.rolling(SMA_FAST, min_periods=SMA_FAST).mean()
    frame["sma200"] = closes.rolling(SMA_SLOW, min_periods=SMA_SLOW).mean()
    frame["sma200_change"] = frame["sma200"] / frame["sma200"].shift(cfg.sma_slope_days) - 1
    fast = closes.ewm(span=MACD_FAST, adjust=False).mean()
    slow = closes.ewm(span=MACD_SLOW, adjust=False).mean()
    frame["macd"] = (fast - slow).where(np.arange(len(closes)) >= MACD_SLOW + MACD_SIGNAL)
    frame["low_52w_prior"] = closes.shift(1).rolling(RANGE_DAYS, min_periods=RANGE_DAYS).min()

    frame[DEATH_CROSS] = (frame["sma50"] < frame["sma200"]).fillna(False)
    frame[BELOW_FALLING_SMA200] = ((closes < frame["sma200"]) & (frame["sma200_change"] < 0)).fillna(False)
    frame[MACD_NEGATIVE] = (frame["macd"] < 0).fillna(False)

    swing = cfg.swing_days
    recent_high = closes.rolling(swing, min_periods=swing).max()
    recent_low = closes.rolling(swing, min_periods=swing).min()
    frame[LOWER_HIGHS_LOWS] = (
        (recent_high < recent_high.shift(swing)) & (recent_low < recent_low.shift(swing))
    ).fillna(False)
    frame[BREAK_52W_LOW] = _recent_event((closes < frame["low_52w_prior"]).fillna(False), cfg.new_lookback_days)

    bench = clean_series(benchmark)
    if bench.empty:
        frame["rs"] = np.nan
        frame[RS_NEW_LOW] = False
    else:
        aligned = bench.reindex(closes.index.union(bench.index)).ffill().reindex(closes.index)
        frame["rs"] = closes / aligned
        prior_low = frame["rs"].shift(1).rolling(cfg.rs_low_days, min_periods=cfg.rs_low_days).min()
        frame[RS_NEW_LOW] = _recent_event((frame["rs"] < prior_low).fillna(False), cfg.new_lookback_days)
    return frame


def active_signals(frame: pd.DataFrame, position: int) -> List[str]:
    """The signals on at row ``position`` of a :func:`signal_frame`."""

    if frame.empty or position < 0 or position >= len(frame):
        return []
    row = frame.iloc[position]
    return [name for name in SIGNALS if bool(row.get(name, False))]


def is_flagged(active: Sequence[str], new: Sequence[str], cfg: TrendWatchConfig) -> bool:
    """Several signals agree, one of them is the price trend, and enough of them are new."""

    return (
        len(active) >= max(cfg.min_signals, 2)
        and len(new) >= max(cfg.min_new_signals, 1)
        and bool(PRICE_TREND_SIGNALS.intersection(active))
    )


def new_signals(active: Sequence[str], earlier: set[str]) -> List[str]:
    """The trigger signals on now that were off in every remembered earlier run."""

    return [name for name in active if name in TRIGGER_SIGNALS and name not in earlier]


def earlier_runs(frame: pd.DataFrame, position: int, cfg: TrendWatchConfig) -> List[List[str]]:
    """The active signals at each of the ``memory_runs`` weekly runs before ``position``, newest first."""

    step = max(cfg.new_lookback_days, 1)
    return [active_signals(frame, position - step * k) for k in range(1, max(cfg.memory_runs, 1) + 1)]


def _num(value: Any, digits: int = 4) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return round(parsed, digits) if np.isfinite(parsed) else None


def _period_return(levels: pd.Series, days: int) -> Optional[float]:
    levels = levels.dropna()
    if len(levels) <= days:
        return None
    return _num(levels.iloc[-1] / levels.iloc[-1 - days] - 1)


def find_artefacts(closes: pd.Series, *, move_threshold: float = price_scale.DEFAULT_LARGE_MOVE_THRESHOLD):
    """Recent price steps and gaps that look like data artefacts rather than trading.

    A ~10x/100x step is a pence/pound flip; any other one-day move larger than
    ``move_threshold`` is most often an unadjusted split. Either can look exactly
    like a collapse, so a holding showing one goes to "data problem, check first".
    So does a run of more than ``GAP_ARTEFACT_DAYS`` missing business days.
    """

    clean = clean_series(closes)
    if clean.empty:
        return []
    recent = clean.iloc[-(ARTEFACT_LOOKBACK_DAYS + 1) :]
    recent.index = [d.date().isoformat() for d in recent.index]
    steps = [dict(step, kind="price_scale_step") for step in price_scale.find_scale_steps(recent)]
    steps += [dict(step, kind="large_one_day_move") for step in price_scale.find_large_moves(recent, move_threshold)]
    frame = pd.DataFrame({"Date": list(recent.index), "Close": recent.to_numpy()})
    steps += [dict(gap, kind="gap", date=gap["start"]) for gap in find_gaps(frame, GAP_ARTEFACT_DAYS)]
    return sorted(steps, key=lambda step: step["date"])


def detect(
    ticker: str,
    closes: pd.Series,
    *,
    benchmark: Optional[pd.Series] = None,
    own_levels: Optional[pd.Series] = None,
    benchmark_levels: Optional[pd.Series] = None,
    return_basis: Optional[str] = None,
    benchmark_return_basis: Optional[str] = None,
    benchmark_ticker: Optional[str] = None,
    previous: Optional[Mapping[str, Any]] = None,
    cfg: Optional[TrendWatchConfig] = None,
    move_threshold: float = price_scale.DEFAULT_LARGE_MOVE_THRESHOLD,
) -> Detection:
    """Read ``ticker``'s chart as of its last close and decide whether to flag it.

    ``closes`` are traded prices. ``own_levels``/``benchmark_levels`` are the
    total-return (or price, per ``*_return_basis``) levels used for relative
    strength and the move comparison; they default to the traded closes.
    ``previous`` is the state saved by the last run (:meth:`Detection.state`);
    without one, the earlier runs are read from the series a week apart.
    """

    cfg = cfg or TrendWatchConfig()
    result = Detection(ticker=ticker)
    closes = clean_series(closes)
    if len(closes) < SMA_SLOW:
        result.reason = f"Only {len(closes)} closes; at least {SMA_SLOW} are needed for the 200-day average."
        if not closes.empty:
            result.as_of = closes.index[-1].date().isoformat()
        return result

    own = clean_series(own_levels) if own_levels is not None else closes
    bench_levels = clean_series(benchmark_levels) if benchmark_levels is not None else clean_series(benchmark)
    frame = signal_frame(closes, bench_levels if not bench_levels.empty else None, cfg)
    last = len(frame) - 1
    result.as_of = frame.index[-1].date().isoformat()
    result.active = active_signals(frame, last)

    earlier, result.values["new_relative_to"] = _earlier(previous, frame, last, cfg)
    result.recent = [list(result.active)] + earlier[: max(cfg.memory_runs, 1) - 1]
    result.new = new_signals(result.active, {name for run in earlier for name in run})
    result.flagged = is_flagged(result.active, result.new, cfg)
    result.values.update(_readings(frame, own, bench_levels, previous, cfg))
    result.values.update(
        {
            # Without total-return levels the comparison runs on traded prices.
            "return_basis": return_basis or ("price" if own_levels is None else None),
            "benchmark": benchmark_ticker,
            "benchmark_return_basis": (benchmark_return_basis or "price") if benchmark_ticker else None,
        }
    )
    # Rank by what changed, not by the level: new signals first, then how far
    # relative strength fell since the last reading.
    result.change_score = round(len(result.new) + max(0.0, -(result.values["rs_change_since_last"] or 0.0)) * 10, 4)
    result.artefacts = find_artefacts(closes, move_threshold=move_threshold)
    result.values["window_start"] = closes.index[-min(len(closes), ARTEFACT_LOOKBACK_DAYS + 1)].date().isoformat()
    return result


def _earlier(
    previous: Optional[Mapping[str, Any]], frame: pd.DataFrame, last: int, cfg: TrendWatchConfig
) -> tuple[List[List[str]], Optional[str]]:
    """The remembered earlier runs (from saved state, else the series) and the date they run back from."""

    if previous and isinstance(previous.get("recent"), list):
        return [[str(n) for n in run] for run in previous["recent"] if isinstance(run, list)], previous.get("as_of")
    if previous and isinstance(previous.get("active"), list):
        return [[str(n) for n in previous["active"]]], previous.get("as_of")
    return earlier_runs(frame, last, cfg), frame.index[max(last - cfg.new_lookback_days, 0)].date().isoformat()


def _readings(
    frame: pd.DataFrame,
    own: pd.Series,
    bench_levels: pd.Series,
    previous: Optional[Mapping[str, Any]],
    cfg: TrendWatchConfig,
) -> Dict[str, Any]:
    """The latest indicator values and the holding-vs-benchmark move behind a detection."""

    last = len(frame) - 1
    row = frame.iloc[last]
    own_move = _period_return(own, MOVE_DAYS)
    bench_move = None
    if not bench_levels.empty:
        bench_move = _period_return(bench_levels[bench_levels.index <= own.index[-1]], MOVE_DAYS)
    rs_now = _num(row.get("rs"), 6)
    rs_before = _num(previous.get("rs"), 6) if previous else None
    if rs_before is None and rs_now is not None:
        rs_before = _num(frame["rs"].iloc[max(last - cfg.new_lookback_days, 0)], 6)
    rs_change = _num(rs_now / rs_before - 1) if rs_now and rs_before else None
    return {
        "price": _num(row["close"]),
        "sma50": _num(row.get("sma50")),
        "sma200": _num(row.get("sma200")),
        "sma200_change": _num(row.get("sma200_change")),
        "macd": _num(row.get("macd")),
        "low_52w_prior": _num(row.get("low_52w_prior")),
        "rs": rs_now,
        "rs_change_since_last": rs_change,
        "move_days": MOVE_DAYS,
        "own_move": own_move,
        "benchmark_move": bench_move,
        "excess_move": _num(own_move - bench_move) if own_move is not None and bench_move is not None else None,
    }


def market_wide(detection: Detection, cfg: Optional[TrendWatchConfig] = None) -> Optional[bool]:
    """Whether the holding fell about as much as its benchmark; ``None`` when there is no comparison."""

    cfg = cfg or TrendWatchConfig()
    own, bench = detection.values.get("own_move"), detection.values.get("benchmark_move")
    if own is None or bench is None:
        return None
    return abs(own - bench) <= cfg.market_move_tolerance
