"""Row builders and rule-based insights for the ``periodic-summary`` report.

Everything here is pure: it turns a :class:`LedgerPerformance` (the ledger
rebuild from :mod:`backend.common.ledger_performance`) and a benchmark close
series into report rows. ``backend.reports`` owns loading, caching and the
section registry.

Ratios are fractions (``0.0123`` is 1.23%), matching ``report_to_pdf``'s
percent convention for ``*_return``/``drawdown``/``weight`` keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from backend.common import ledger_performance as lp
from backend.common.ledger_performance import LedgerPerformance

Row = Dict[str, Any]

# ──────────────────────────────────────────────────────────────
# Insight thresholds (fractions unless noted)
# ──────────────────────────────────────────────────────────────
# |portfolio - benchmark| over the year to date.
BENCHMARK_GAP_THRESHOLD = 0.02
# One holding's share of total value.
SINGLE_HOLDING_WEIGHT_THRESHOLD = 0.20
# Herfindahl-Hirschman index of invested (non-cash) weights; 0.15 is roughly
# fewer than seven equal-sized holdings.
HHI_THRESHOLD = 0.15
# Current fall from the TWR peak that has not been recovered.
DRAWDOWN_THRESHOLD = 0.10
# Share of the month's net P&L coming from one holding ...
SINGLE_DRIVER_SHARE_THRESHOLD = 0.60
# ... only judged when the month moved at least this much, since a share of a
# near-zero month is meaningless.
SINGLE_DRIVER_MIN_MOVE = 0.005
# Cash share of total value.
CASH_WEIGHT_THRESHOLD = 0.10

CONTRIBUTOR_COUNT = 3


# ──────────────────────────────────────────────────────────────
# Periods
# ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Period:
    """A reporting period valued from the close of ``base`` to the close of ``end``."""

    key: str
    label: str
    base: Optional[date]
    end: date
    annualised: bool = False


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    following = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return following - timedelta(days=1)


def reporting_periods(end: date, inception: Optional[date]) -> List[Period]:
    """Month containing ``end``, YTD, 1Y, since inception and its annualised form.

    Labels are kept short enough for the PDF's equal-width table columns; the
    ``key`` is the stable identifier (rows carry it as ``period_key``).
    """
    month_label = f"{end:%b %Y}" if end == _month_end(end) else f"{end:%b %Y} (MTD)"
    inception_base = inception - timedelta(days=1) if inception else None
    return [
        Period("month", month_label, _month_start(end) - timedelta(days=1), end),
        Period("ytd", f"YTD {end.year}", date(end.year, 1, 1) - timedelta(days=1), end),
        Period("1y", "1 year", lp.one_year_before(end), end),
        Period("inception", "Since inception", inception_base, end),
        Period("inception_annualised", "Since inception p.a.", inception_base, end, annualised=True),
    ]


def _effective_base(base: Optional[date], inception: Optional[date]) -> Optional[date]:
    """Clamp a period's base to the day before inception (a period cannot start earlier)."""
    if inception is None:
        return base
    floor = inception - timedelta(days=1)
    return floor if base is None or base < floor else base


def _round(value: Optional[float], digits: int = 6) -> Optional[float]:
    return None if value is None else round(float(value), digits)


def _excess(portfolio: Optional[float], benchmark: Optional[float]) -> Optional[float]:
    if portfolio is None or benchmark is None:
        return None
    return portfolio - benchmark


def _period_returns(
    period: Period, perf: Optional[LedgerPerformance], closes: Optional[pd.Series]
) -> tuple[Optional[date], Optional[float], Optional[float]]:
    """Return ``(effective_base, portfolio_return, benchmark_return)`` for ``period``."""
    inception = perf.inception if perf else None
    base = _effective_base(period.base, inception)
    if base is None:
        return None, None, None
    portfolio = lp.chained_return(perf.returns, base, period.end) if perf else None
    benchmark = lp.price_return(closes, base, period.end) if closes is not None and not closes.empty else None
    if period.annualised:
        days = (period.end - base).days
        portfolio, benchmark = lp.annualise(portfolio, days), lp.annualise(benchmark, days)
    return base, portfolio, benchmark


def period_rows(perf: Optional[LedgerPerformance], closes: Optional[pd.Series], end: date) -> List[Row]:
    """One row per headline period; return columns are ``None`` when not computable."""
    rows: List[Row] = []
    for period in reporting_periods(end, perf.inception if perf else None):
        base, portfolio, benchmark = _period_returns(period, perf, closes)
        rows.append(
            {
                "period": period.label,
                "period_key": period.key,
                "start": (base + timedelta(days=1)).isoformat() if base else None,
                "end": period.end.isoformat(),
                "portfolio_return": _round(portfolio),
                "benchmark_return": _round(benchmark),
                "excess_return": _round(_excess(portfolio, benchmark)),
            }
        )
    return rows


def _trailing_months(end: date, count: int = 12) -> List[date]:
    months = [_month_start(end)]
    while len(months) < count:
        months.append(_month_start(months[-1] - timedelta(days=1)))
    return list(reversed(months))


def monthly_rows(perf: Optional[LedgerPerformance], closes: Optional[pd.Series], end: date) -> List[Row]:
    """Trailing twelve calendar months to ``end`` (which covers the whole reporting year)."""
    rows: List[Row] = []
    for month in _trailing_months(end):
        base = month - timedelta(days=1)
        through = min(_month_end(month), end)
        year_base = date(month.year, 1, 1) - timedelta(days=1)
        portfolio = cumulative = None
        if perf is not None and through >= perf.inception:
            portfolio = lp.chained_return(perf.returns, base, through)
            cumulative = lp.chained_return(perf.returns, year_base, through)
        benchmark = lp.price_return(closes, base, through) if closes is not None and not closes.empty else None
        rows.append(
            {
                "month": f"{month:%Y-%m}",
                "portfolio_return": _round(portfolio),
                "cumulative_ytd_return": _round(cumulative),
                "benchmark_return": _round(benchmark),
            }
        )
    return rows


# ──────────────────────────────────────────────────────────────
# Risk
# ──────────────────────────────────────────────────────────────
def _risk_row(
    key: str,
    metric: str,
    value: Optional[float],
    units: str,
    window: str,
    *,
    peak: Optional[date] = None,
    trough: Optional[date] = None,
) -> Row:
    return {
        "key": key,
        "metric": metric,
        "value": _round(value),
        "units": units,
        "window": window,
        "peak_date": peak.isoformat() if peak else None,
        "trough_date": trough.isoformat() if trough else None,
    }


def risk_rows(perf: Optional[LedgerPerformance], end: date, risk_free_rate: float) -> List[Row]:
    """Volatility and Sharpe over the trailing year; drawdowns of the TWR wealth index."""
    if perf is None:
        return []
    year_base = _effective_base(lp.one_year_before(end), perf.inception)
    volatility = lp.annualised_volatility(perf.returns, year_base, end)
    sharpe = lp.sharpe_ratio(perf.returns, year_base, end, risk_free_rate)
    rows = [
        _risk_row("volatility", "Volatility (p.a.)", volatility, "fraction", "1Y"),
        _risk_row("sharpe", "Sharpe ratio", sharpe, "number", "1Y"),
    ]
    for key, window, base in (("max_drawdown_1y", "1Y", year_base), ("max_drawdown", "Since inception", None)):
        dd = lp.drawdown(perf.returns, base, end)
        if dd is not None:
            rows.append(
                _risk_row(key, "Max drawdown", dd.max_drawdown, "fraction", window, peak=dd.peak, trough=dd.trough)
            )
    since_inception = lp.drawdown(perf.returns, None, end)
    if since_inception is not None:
        rows.append(
            _risk_row(
                "current_drawdown",
                "Current drawdown",
                since_inception.current_drawdown,
                "fraction",
                "Since inception",
                peak=since_inception.current_peak,
            )
        )
    return rows


# ──────────────────────────────────────────────────────────────
# Contributors
# ──────────────────────────────────────────────────────────────
def _contributor_rows(
    perf: LedgerPerformance, period: Period, base: Optional[date], weights: Mapping[str, float]
) -> List[Row]:
    frame = lp.contributions(perf, base, period.end).sort_values("contribution", ascending=False)
    # Top lists only holdings that added to the return, Bottom only those that
    # took from it, so a quiet month shows fewer rows rather than a "top"
    # contributor that lost money.
    gainers = frame[frame["pnl_gbp"] > 0.005].head(CONTRIBUTOR_COUNT)
    losers = frame[frame["pnl_gbp"] < -0.005].tail(CONTRIBUTOR_COUNT).iloc[::-1]
    picks = (("Top", gainers), ("Bottom", losers))
    rows: List[Row] = []
    for direction, chosen in picks:
        for rank, (key, item) in enumerate(chosen.iterrows(), start=1):
            rows.append(
                {
                    "period": period.label,
                    "period_key": period.key,
                    "direction": direction,
                    "rank": rank,
                    "ticker": key,
                    "name": perf.names.get(str(key)),
                    "contribution_gbp": _round(item["pnl_gbp"], 2),
                    "contribution_return": _round(item["contribution"]),
                    "weight": _round(weights.get(str(key), 0.0)),
                }
            )
    return rows


def contributor_rows(perf: Optional[LedgerPerformance], end: date) -> List[Row]:
    """Top and bottom holdings by contribution, for the reporting month and the year to date."""
    if perf is None:
        return []
    weighted = lp.weights_at(perf, end)
    weights = weighted[0] if weighted else {}
    rows: List[Row] = []
    for period in reporting_periods(end, perf.inception)[:2]:
        base = _effective_base(period.base, perf.inception)
        rows.extend(_contributor_rows(perf, period, base, weights))
    return rows


# ──────────────────────────────────────────────────────────────
# Insights: each rule is pure over the computed section data and returns at
# most one finding.
# ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class InsightInputs:
    periods: Sequence[Row] = ()
    risk: Sequence[Row] = ()
    contributors: Sequence[Row] = ()
    weights: Mapping[str, float] = field(default_factory=dict)
    cash_weight: Optional[float] = None
    benchmark: Optional[str] = None
    has_ledger: bool = True
    unreconciled: Sequence[str] = ()
    unpriced: Sequence[str] = ()
    # Priced instruments with dates that had no GBP close for want of an FX rate (#9759).
    fx_gaps: Sequence[str] = ()


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _row(rows: Sequence[Row], field_name: str, value: str) -> Optional[Row]:
    return next((row for row in rows if row.get(field_name) == value), None)


def rule_benchmark_gap(inputs: InsightInputs) -> Optional[str]:
    row = _row(inputs.periods, "period_key", "ytd")
    excess = row.get("excess_return") if row else None
    if row is None or excess is None or abs(excess) < BENCHMARK_GAP_THRESHOLD:
        return None
    direction = "ahead of" if excess > 0 else "behind"
    return (
        f"Year to date the portfolio is {_pct(abs(excess))} {direction} the {inputs.benchmark or 'benchmark'} "
        f"benchmark ({_pct(row['portfolio_return'])} vs {_pct(row['benchmark_return'])})."
    )


def rule_single_holding_weight(inputs: InsightInputs) -> Optional[str]:
    if not inputs.weights:
        return None
    ticker, weight = max(inputs.weights.items(), key=lambda item: item[1])
    if weight < SINGLE_HOLDING_WEIGHT_THRESHOLD:
        return None
    return (
        f"{ticker} is {_pct(weight)} of the portfolio, above the "
        f"{_pct(SINGLE_HOLDING_WEIGHT_THRESHOLD)} single-holding guide."
    )


def rule_hhi(inputs: InsightInputs) -> Optional[str]:
    invested = sum(inputs.weights.values())
    if invested <= 0:
        return None
    hhi = sum((weight / invested) ** 2 for weight in inputs.weights.values())
    if hhi < HHI_THRESHOLD:
        return None
    equivalent = 1 / hhi
    return (
        f"Concentration is high (HHI {hhi:.2f}): the invested portfolio behaves like "
        f"about {equivalent:.1f} equal-sized holdings."
    )


def rule_unrecovered_drawdown(inputs: InsightInputs) -> Optional[str]:
    row = _row(inputs.risk, "key", "current_drawdown")
    depth = row.get("value") if row else None
    if row is None or depth is None or -depth < DRAWDOWN_THRESHOLD:
        return None
    return f"The portfolio is {_pct(-depth)} below its peak of {row['peak_date']} and has not yet recovered."


def rule_single_driver(inputs: InsightInputs) -> Optional[str]:
    month = _row(inputs.periods, "period_key", "month")
    move = month.get("portfolio_return") if month else None
    if month is None or move is None or abs(move) < SINGLE_DRIVER_MIN_MOVE:
        return None
    rows = [
        row
        for row in inputs.contributors
        if row.get("period_key") == "month" and row.get("contribution_return") is not None
    ]
    if not rows:
        return None
    sign = 1.0 if move > 0 else -1.0
    driver = max(rows, key=lambda row: row["contribution_return"] * sign)
    share = driver["contribution_return"] / move
    if share < SINGLE_DRIVER_SHARE_THRESHOLD:
        return None
    verb = "gain" if move > 0 else "loss"
    return (
        f"{driver['ticker']} drove {_pct(share)} of this month's {verb} "
        f"({_pct(driver['contribution_return'])} of {_pct(move)})."
    )


def rule_cash_drag(inputs: InsightInputs) -> Optional[str]:
    if inputs.cash_weight is None or inputs.cash_weight < CASH_WEIGHT_THRESHOLD:
        return None
    return (
        f"Cash is {_pct(inputs.cash_weight)} of the portfolio, above the {_pct(CASH_WEIGHT_THRESHOLD)} guide; "
        "uninvested cash can drag on returns."
    )


def _display(keys: Sequence[str], limit: int = 5) -> str:
    """Readable, capped list of ledger instrument keys (``name:``/``ref:`` keys have no ticker)."""
    labels = []
    for key in keys:
        if key.startswith("name:"):
            labels.append(key[len("name:") :].title())
        elif key.startswith("ref:"):
            labels.append(f"unidentified security {key[len('ref:') :]}")
        else:
            labels.append(key)
    shown = ", ".join(labels[:limit])
    return shown if len(labels) <= limit else f"{shown} and {len(labels) - limit} more"


def rule_data_coverage(inputs: InsightInputs) -> Optional[str]:
    if not inputs.has_ledger:
        return "No transaction ledger was found, so portfolio returns cannot be calculated; benchmark figures only."
    gaps = []
    if inputs.unreconciled:
        gaps.append(f"holdings the ledger does not reproduce ({_display(inputs.unreconciled)}) are excluded")
    if inputs.unpriced:
        gaps.append(f"instruments without price history ({_display(inputs.unpriced)}) are valued at trade prices")
    if inputs.fx_gaps:
        gaps.append(
            f"instruments with no FX rate on some dates ({_display(inputs.fx_gaps)}) "
            "keep their last converted price on those dates"
        )
    if not gaps:
        return None
    return "Return history is approximate: " + "; ".join(gaps) + "."


INSIGHT_RULES: Sequence[Callable[[InsightInputs], Optional[str]]] = (
    rule_data_coverage,
    rule_benchmark_gap,
    rule_single_holding_weight,
    rule_hhi,
    rule_unrecovered_drawdown,
    rule_single_driver,
    rule_cash_drag,
)


def insight_rows(inputs: InsightInputs) -> List[Row]:
    """Run every rule in order and keep the findings that fired."""
    findings = (rule(inputs) for rule in INSIGHT_RULES)
    return [{"finding": finding} for finding in findings if finding]
