"""One trend-watch run for one owner: detect, check the data, investigate, report (#10476).

:func:`run_for_owner` is the whole job. The route (``POST /trend-watch/{owner}/run``)
and the weekly Lambda both call it, and it is the function a scheduler or bot
registry would wrap. It:

1. reads the owner's priced holdings and each one's cached daily closes;
2. runs the detector against the state the previous run saved, then saves the
   new state, so next week's "new" means new since today;
3. sends every flagged holding through the data check; one with an open issue
   or an artefact in its series is "data problem, check first";
4. investigates the rest, highest change first, up to ``max_investigated``;
5. adds the owner's context (value, share, wrapper, book cost, muted);
6. backtests the detector over the holdings' histories;
7. stores the report and, if asked, sends a short alert.

It never trades and writes only its own report, state and mute documents.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import pandas as pd

from backend.common.core_optional import missing_package
from backend.common.instruments import get_instrument_meta
from backend.common.ticker_utils import split_ticker
from backend.config import TrendWatchConfig
from backend.data_quality import price_scale
from backend.logging_setup import sanitise_log_value
from backend.trend_watch import agent, data_gate, prompt, storage
from backend.trend_watch.backtest import Series, backtest
from backend.trend_watch.detect import Detection, detect
from backend.trend_watch.settings import load_trend_watch_config

logger = logging.getLogger(__name__)

# Five years: the detector needs about two, the backtest uses the rest.
HISTORY_DAYS = 5 * 365
TAX_FREE_WRAPPERS = ("ISA", "SIPP", "PENSION")
NON_TRADED_TYPES = {"cash", "money market", "savings"}

VERDICT_LABELS = {
    prompt.VERDICT_IDIOSYNCRATIC: "Idiosyncratic deterioration",
    prompt.VERDICT_MARKET: "Market-wide move",
    prompt.VERDICT_DATA: "Data problem, check first",
    prompt.VERDICT_INCONCLUSIVE: "Inconclusive",
}

# Benchmarks when allotmint-pro's resolver is not installed; the same defaults it uses.
_FALLBACK_BENCHMARKS = {
    "L": "FTAL.L",
    "N": "VUSA.L",
    "O": "VUSA.L",
    "OQ": "VUSA.L",
    "NASDAQ": "VUSA.L",
    "NYSE": "VUSA.L",
}
_GLOBAL_BENCHMARK = "VWRL.L"

PriceLoader = Callable[[str, int], pd.Series]
LevelsLoader = Callable[[pd.Series, str], Tuple[pd.Series, str]]


def default_price_loader(ticker: str, days: int) -> pd.Series:
    """Daily closes for ``ticker`` from the app's timeseries cache, oldest first."""

    from backend.timeseries.cache import load_meta_timeseries

    symbol, exchange = split_ticker(ticker)
    df = load_meta_timeseries(symbol, exchange or "", days)
    if df is None or df.empty or "Close" not in df or "Date" not in df:
        return pd.Series(dtype=float)
    return pd.Series(pd.to_numeric(df["Close"], errors="coerce").to_numpy(), index=pd.to_datetime(df["Date"]))


def default_levels_loader(closes: pd.Series, ticker: str) -> Tuple[pd.Series, str]:
    """Total-return levels (stored dividends reinvested) and their ``return_basis``."""

    from backend.timeseries.total_return import total_return_closes_for

    return total_return_closes_for(closes, ticker)


def resolve_benchmark(ticker: str, meta: Mapping[str, Any]) -> Optional[str]:
    """The comparison benchmark, as allotmint-pro's valuation profile picks it when installed."""

    try:
        from allotmint_pro.screener.valuation import resolve_benchmark as pro_resolve
    except ModuleNotFoundError as exc:
        if not missing_package(exc):
            raise
        pro_resolve = None
    if pro_resolve is not None:
        return pro_resolve(ticker, dict(meta)).ticker
    override = meta.get("benchmark")
    if isinstance(override, str) and override.strip():
        return override.strip().upper()
    kind = str(meta.get("instrument_type") or meta.get("asset_class") or "").lower()
    if any(word in kind for word in ("bond", "gilt", "cash", "commodity", "money market")):
        return None
    _, exchange = split_ticker(ticker)
    return _FALLBACK_BENCHMARKS.get((exchange or "").upper(), _GLOBAL_BENCHMARK)


def _is_tax_free(account_type: str) -> bool:
    upper = (account_type or "").upper()
    return any(word in upper for word in TAX_FREE_WRAPPERS)


def holdings_by_ticker(portfolio: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The owner's traded holdings combined across accounts, with value, book cost and wrappers."""

    total = float(portfolio.get("total_value_estimate_gbp") or 0.0)
    out: Dict[str, Dict[str, Any]] = {}
    for account in portfolio.get("accounts") or []:
        account_type = str(account.get("account_type") or "")
        for holding in account.get("holdings") or []:
            ticker = str(holding.get("ticker") or "").upper()
            kind = str(holding.get("instrument_type") or "").lower()
            if not ticker or ticker.startswith("CASH") or kind in NON_TRADED_TYPES:
                continue
            entry = out.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "name": holding.get("name"),
                    "instrument_type": holding.get("instrument_type"),
                    "market_value_gbp": 0.0,
                    "cost_basis_gbp": 0.0,
                    "accounts": [],
                },
            )
            entry["market_value_gbp"] += float(holding.get("market_value_gbp") or 0.0)
            entry["cost_basis_gbp"] += float(
                holding.get("cost_basis_gbp") or holding.get("effective_cost_basis_gbp") or 0.0
            )
            entry["accounts"].append({"account_type": account_type, "tax_free": _is_tax_free(account_type)})
    for entry in out.values():
        value, cost = entry["market_value_gbp"], entry["cost_basis_gbp"]
        entry["market_value_gbp"] = round(value, 2)
        entry["cost_basis_gbp"] = round(cost, 2)
        entry["portfolio_share"] = round(value / total, 4) if total else None
        entry["gain_gbp"] = round(value - cost, 2) if cost else None
        entry["gain_pct"] = round(value / cost - 1, 4) if cost else None
        taxable = [a["account_type"] for a in entry["accounts"] if not a["tax_free"]]
        entry["cgt_note"] = (
            f"Held in {', '.join(sorted(set(taxable)))}: a disposal there could be liable to capital gains tax."
            if taxable
            else "Held only in ISA/SIPP wrappers: no capital gains tax on a disposal."
        )
    return out


def _empty_report(owner: str, today: date) -> Dict[str, Any]:
    return {
        "owner": owner,
        "run_date": today.isoformat(),
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "disclaimer": prompt.DISCLAIMER,
        "holdings_checked": 0,
        "items": [],
        "skipped": [],
        "data_check_errors": [],
        "backtest": None,
    }


def _load_series(
    ticker: str, load_prices: PriceLoader, load_levels: LevelsLoader, cache: Dict[str, Tuple[pd.Series, pd.Series, str]]
) -> Tuple[pd.Series, pd.Series, str]:
    """``(closes, levels, return_basis)`` for ``ticker``, loaded once per run."""

    if ticker not in cache:
        closes = load_prices(ticker, HISTORY_DAYS)
        if closes is None or closes.empty:
            cache[ticker] = (pd.Series(dtype=float), pd.Series(dtype=float), "price")
        else:
            levels, basis = load_levels(closes, ticker)
            cache[ticker] = (closes, levels, basis)
    return cache[ticker]


def _detect_all(
    holdings: Mapping[str, Mapping[str, Any]],
    previous_state: Mapping[str, Mapping[str, Any]],
    cfg: TrendWatchConfig,
    load_prices: PriceLoader,
    load_levels: LevelsLoader,
    load_meta: Callable[[str], Mapping[str, Any]],
    report: Dict[str, Any],
) -> Tuple[Dict[str, Detection], Dict[str, Series]]:
    detections: Dict[str, Detection] = {}
    histories: Dict[str, Series] = {}
    cache: Dict[str, Tuple[pd.Series, pd.Series, str]] = {}
    for ticker in holdings:
        try:
            meta = load_meta(ticker) or {}
            closes, levels, basis = _load_series(ticker, load_prices, load_levels, cache)
            if closes.empty:
                report["skipped"].append({"ticker": ticker, "reason": "no cached price history"})
                continue
            bench_ticker = resolve_benchmark(ticker, meta)
            bench_closes, bench_levels, bench_basis = (
                _load_series(bench_ticker, load_prices, load_levels, cache) if bench_ticker else (None, None, None)
            )
            if bench_closes is not None and bench_closes.empty:
                bench_ticker, bench_levels, bench_basis = None, None, None
            detection = detect(
                ticker,
                closes,
                own_levels=levels,
                benchmark_levels=bench_levels,
                return_basis=basis,
                benchmark_return_basis=bench_basis,
                benchmark_ticker=bench_ticker,
                previous=previous_state.get(ticker),
                cfg=cfg,
                move_threshold=price_scale.large_move_threshold(dict(meta)),
            )
        except Exception as exc:  # noqa: BLE001 - one bad series is reported, not fatal to the run
            logger.warning(
                "Trend-watch detection failed for %s: %s", sanitise_log_value(ticker), sanitise_log_value(exc)
            )
            report["skipped"].append({"ticker": ticker, "reason": f"detection failed: {type(exc).__name__}: {exc}"})
            continue
        if detection.reason:
            report["skipped"].append({"ticker": ticker, "reason": detection.reason})
        detections[ticker] = detection
        histories[ticker] = Series(closes=closes, levels=levels, benchmark_levels=bench_levels, return_basis=basis)
    return detections, histories


def _item(holding: Mapping[str, Any], detection: Detection, muted: bool) -> Dict[str, Any]:
    context = {
        key: holding.get(key)
        for key in (
            "market_value_gbp",
            "portfolio_share",
            "cost_basis_gbp",
            "gain_gbp",
            "gain_pct",
            "accounts",
            "cgt_note",
        )
    }
    context["muted"] = muted
    return {
        "ticker": detection.ticker,
        "name": holding.get("name"),
        "instrument_type": holding.get("instrument_type"),
        "muted": muted,
        "change_score": detection.change_score,
        "detection": detection.to_dict(),
        "context": context,
    }


def _finish(item: Dict[str, Any], verdict: str, investigation: Dict[str, Any]) -> Dict[str, Any]:
    item["verdict"] = verdict
    item["verdict_label"] = VERDICT_LABELS[verdict]
    item["investigation"] = investigation
    return item


async def _assess(
    flagged: List[Dict[str, Any]],
    detections: Mapping[str, Detection],
    cfg: TrendWatchConfig,
    runner: Optional[agent.Runner],
    load_issues: Callable[[], Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]],
    report: Dict[str, Any],
) -> List[Dict[str, Any]]:
    issues, errors = load_issues() if flagged else ([], [])
    report["data_check_errors"] = errors
    clean: List[Dict[str, Any]] = []
    done: List[Dict[str, Any]] = []
    for item in flagged:
        detection = detections[item["ticker"]]
        problems = data_gate.gate(item["ticker"], issues, detection.artefacts, detection.values.get("window_start"))
        if problems:
            item["data_issues"] = problems
            done.append(
                _finish(
                    item,
                    prompt.VERDICT_DATA,
                    {
                        "status": "skipped",
                        "summary": None,
                        "evidence": [],
                        "tool_calls": [],
                        "notes": ["Not investigated: the price data needs checking first."],
                    },
                )
            )
        else:
            clean.append(item)
    # Unmuted holdings first, then the biggest change, within the investigation cap.
    clean.sort(key=lambda it: (it["muted"], -it["change_score"]))
    for index, item in enumerate(clean):
        detection = detections[item["ticker"]]
        if index < cfg.max_investigated:
            result = await agent.investigate(item, detection, cfg=cfg, runner=runner)
        else:
            result = {
                "status": "not_run",
                "verdict": agent.fallback_verdict(detection, cfg),
                "summary": None,
                "evidence": agent.detector_evidence(detection),
                "tool_calls": [],
                "notes": [f"Not investigated: only the top {cfg.max_investigated} holdings are investigated per run."],
            }
        verdict = result.pop("verdict")
        done.append(_finish(item, verdict, result))
    return done


def alert_text(report: Mapping[str, Any]) -> Optional[str]:
    """A short, instruction-free alert listing the unmuted holdings to review, or ``None``."""

    items = [item for item in report.get("items") or [] if not item.get("muted")]
    if not items:
        return None
    lines = [f"Trend watch for {report.get('owner')}: {len(items)} holding(s) to review."]
    lines += [f"- {item['ticker']}: {item['verdict_label']}" for item in items]
    lines.append("A review list, not trade instructions.")
    return "\n".join(lines)


async def run_for_owner(
    owner: str,
    *,
    notify: bool = False,
    today: Optional[date] = None,
    cfg: Optional[TrendWatchConfig] = None,
    runner: Optional[agent.Runner] = None,
    load_portfolio: Optional[Callable[[str], Mapping[str, Any]]] = None,
    load_prices: PriceLoader = default_price_loader,
    load_levels: LevelsLoader = default_levels_loader,
    load_meta: Callable[[str], Mapping[str, Any]] = lambda ticker: get_instrument_meta(ticker) or {},
    load_issues: Callable[[], Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]] = data_gate.load_open_issues,
) -> Dict[str, Any]:
    """Run trend watch for ``owner``, store the report and return it. The loaders are injectable for tests."""

    cfg = cfg or load_trend_watch_config()
    today = today or date.today()
    if load_portfolio is None:
        from backend.common.portfolio import build_owner_portfolio

        load_portfolio = build_owner_portfolio
    report = _empty_report(owner, today)
    holdings = holdings_by_ticker(load_portfolio(owner))
    report["holdings_checked"] = len(holdings)
    mutes = set(storage.load_mutes(owner))
    detections, histories = _detect_all(
        holdings, storage.load_state(owner), cfg, load_prices, load_levels, load_meta, report
    )
    storage.save_state(
        owner, {ticker: detection.state() for ticker, detection in detections.items() if detection.as_of}
    )

    flagged = [_item(holdings[t], d, t in mutes) for t, d in detections.items() if d.flagged]
    items = await _assess(flagged, detections, cfg, runner, load_issues, report)
    order = {
        prompt.VERDICT_IDIOSYNCRATIC: 0,
        prompt.VERDICT_INCONCLUSIVE: 1,
        prompt.VERDICT_MARKET: 2,
        prompt.VERDICT_DATA: 3,
    }
    items.sort(key=lambda it: (it["muted"], order[it["verdict"]], -it["change_score"]))
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    report["items"] = items
    report["not_flagged"] = len(detections) - len(flagged)
    report["mutes"] = sorted(mutes)
    report["backtest"] = backtest(histories, cfg)
    report["settings"] = {
        "min_signals": cfg.min_signals,
        "min_new_signals": cfg.min_new_signals,
        "max_investigated": cfg.max_investigated,
        "max_tool_calls": cfg.max_tool_calls,
    }
    storage.save_report(owner, report)
    if notify:
        text = alert_text(report)
        if text:
            from backend.agent.trading_agent import send_trade_alert

            send_trade_alert(text)
    return report
