"""Utility helpers for scenario testing.

Includes helpers for price shocks and applying historical events to
portfolios.
"""

from __future__ import annotations

import datetime as dt
import math
from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping

import pandas as pd

from backend.common.constants import (
    COST_BASIS_GBP,
    EFFECTIVE_COST_BASIS_GBP,
)
from backend.common.portfolio_utils import (
    FX_MISSING_ALL_DATES,
    UNCONVERTED_HOLDINGS_KEY,
    UNKNOWN_CURRENCY_LABEL,
    holding_quote_currency,
)
from backend.common.prices import get_price_gbp
from backend.common.sector_labels import is_cash_instrument
from backend.timeseries.cache import load_meta_timeseries_range
from backend.timeseries.total_return import PRICE_RETURN_BASIS, TOTAL_RETURN_BASIS, total_return_frame
from backend.utils.fx_rates import FX_RATE_SOURCE_MISSING
from backend.utils.timeseries_helpers import (
    apply_scaling,
    get_scaling_override,
)


def _cost_basis(holding: Dict[str, Any]) -> float:
    return float(holding.get(EFFECTIVE_COST_BASIS_GBP) or holding.get(COST_BASIS_GBP) or 0.0)


def _revalue_holding(holding: Dict[str, Any], market_value: float, change: float, *, gain_known: bool = True) -> None:
    """Store a holding's shocked GBP ``market_value`` and the fields that follow from it.

    ``change`` (the shock's effect on the holding) is reported as
    ``day_change_gbp``. With ``gain_known`` False the gain fields stay
    unknown (``None``) instead of being computed from a missing cost.
    """
    holding["market_value_gbp"] = round(market_value, 2)
    holding["day_change_gbp"] = round(change, 2)
    if not gain_known:
        return
    cost = _cost_basis(holding)
    gain = market_value - cost
    holding["gain_gbp"] = round(gain, 2)
    holding["unrealised_gain_gbp"] = holding["unrealized_gain_gbp"] = round(gain, 2)
    holding["gain_pct"] = round((gain / cost * 100.0), 2) if cost else None


def _recompute_totals(portfolio: Dict[str, Any]) -> None:
    """Recompute each account's ``value_estimate_gbp`` and the portfolio total from its holdings."""
    for acct in portfolio.get("accounts", []):
        total = sum(float(h.get("market_value_gbp") or 0.0) for h in acct.get("holdings", []))
        acct["value_estimate_gbp"] = round(total, 2)
    portfolio["total_value_estimate_gbp"] = round(
        sum(a.get("value_estimate_gbp") or 0.0 for a in portfolio.get("accounts", [])),
        2,
    )


def apply_price_shock(portfolio: Dict[str, Any], ticker: str, pct_change: float) -> Dict[str, Any]:
    """Return a new portfolio with ``ticker`` shocked by ``pct_change`` percent.

    ``pct_change`` is interpreted as a percentage (e.g. ``5`` for +5%).
    The function recalculates affected holding metrics, account totals and the
    overall portfolio total.  The original ``portfolio`` is not modified.
    """

    shocked = deepcopy(portfolio)
    target = ticker.upper()
    factor = 1 + pct_change / 100.0

    for acct in shocked.get("accounts", []):
        for h in acct.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if tkr != target:
                continue
            units = float(h.get("units") or 0.0)
            price = float(h.get("current_price_gbp") or h.get("price") or 0.0)
            if price == 0:
                cached = get_price_gbp(tkr)
                price = float(cached or 0.0)
            new_price = price * factor
            h["price"] = h["current_price_gbp"] = round(new_price, 4)
            _revalue_holding(h, units * new_price, (new_price - price) * units)

    _recompute_totals(shocked)
    return shocked


# Key under which apply_fx_shock reports what it did on the returned portfolio.
FX_SHOCK_KEY = "fx_shock"

# Quote currencies an FX shock against sterling cannot move (GBX is pence).
NON_SHOCKABLE_CURRENCIES = frozenset({"GBP", "GBX"})


def _fx_rate_missing(holding: Dict[str, Any]) -> bool:
    return holding.get("fx_rate_source") == FX_RATE_SOURCE_MISSING


def _unconverted_entry(holding: Dict[str, Any], currency: str) -> Dict[str, Any]:
    """An ``unconverted_holdings`` entry in the #9671 shape."""
    return {"ticker": str(holding.get("ticker") or ""), "currency": currency, "reason": FX_MISSING_ALL_DATES}


def apply_fx_shock(portfolio: Dict[str, Any], currency: str, pct_change: float) -> Dict[str, Any]:
    """Return a new portfolio revalued for ``currency`` moving ``pct_change`` percent against GBP.

    Sign convention: ``pct_change`` is the change in the GBP value of one unit
    of ``currency``. ``currency="USD", pct_change=-10`` means USD weakens 10%
    against GBP, so every holding *quoted* in USD (``CASH.USD`` included) is
    worth 0.9x its GBP value. Native prices do not change, and GBP/GBX
    holdings never move. The quote currency is resolved exactly as
    :func:`backend.common.portfolio_utils.aggregate_by_currency` buckets it.

    Like :func:`apply_price_shock`, holding metrics and account/portfolio
    totals are recomputed on a deep copy. Holdings with no usable FX rate
    (``fx_rate_source == "missing"``) are neither shocked nor summed into any
    total; they are listed under ``UNCONVERTED_HOLDINGS_KEY``. Holdings whose
    currency cannot be resolved are not shocked and are counted (they stay in
    both totals). Unpriced holdings (``market_value_gbp is None`` for want of
    a price, not an FX rate) count as zero, as in every portfolio total.
    ``day_change_gbp`` on a shocked holding is the shock's change to its GBP
    value, as in :func:`apply_price_shock`.

    The returned portfolio carries a summary under ``FX_SHOCK_KEY``:
    ``currency``, ``pct``, ``baseline_total_value_gbp``,
    ``exposed_value_gbp`` (baseline GBP value of the shocked holdings),
    ``skipped_unknown_currency`` and ``UNCONVERTED_HOLDINGS_KEY``.

    Raises ``ValueError`` for GBP/GBX, which cannot move against GBP.
    """

    target = currency.strip().upper()
    if target in NON_SHOCKABLE_CURRENCIES:
        raise ValueError(f"{target} cannot be shocked against GBP")
    factor = 1 + pct_change / 100.0
    shocked = deepcopy(portfolio)
    baseline = exposed = 0.0
    skipped_unknown = 0
    unconverted: Dict[str, Dict[str, Any]] = {}

    for acct in shocked.get("accounts", []):
        for h in acct.get("holdings", []):
            quote = holding_quote_currency(h)
            if _fx_rate_missing(h):
                # Left out of every total, never valued at a made-up rate (#9664).
                h["market_value_gbp"] = None
                entry = _unconverted_entry(h, quote)
                unconverted.setdefault(entry["ticker"], entry)
                continue
            value = h.get("market_value_gbp")
            if value is None:
                continue
            value = float(value)
            baseline += value
            if quote == UNKNOWN_CURRENCY_LABEL:
                skipped_unknown += 1
                continue
            if quote != target:
                continue
            exposed += value
            price = h.get("current_price_gbp")
            if price is not None:
                h["current_price_gbp"] = round(float(price) * factor, 4)
            _revalue_holding(h, value * factor, value * (factor - 1), gain_known=h.get("gain_gbp") is not None)

    _recompute_totals(shocked)
    shocked[FX_SHOCK_KEY] = {
        "currency": target,
        "pct": pct_change,
        "baseline_total_value_gbp": round(baseline, 2),
        "exposed_value_gbp": round(exposed, 2),
        "skipped_unknown_currency": skipped_unknown,
        UNCONVERTED_HOLDINGS_KEY: list(unconverted.values()),
    }
    return shocked


# ---------------------------------------------------------------------------
# Historical event application

_HORIZONS: Dict[str, int] = {
    "1d": 1,
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "1y": 365,
}


def _parse_full_ticker(full: str | Dict[str, str]) -> tuple[str, str]:
    """Split a ticker/exchange combination into its components.

    ``full`` can either be a mapping containing ``ticker`` and ``exchange``
    keys or a string in the format ``"SYMBOL.EXCH"``.  The return value is a
    2-tuple of ``(ticker, exchange)`` with the exchange defaulting to ``"L"``
    (London) when not provided.
    """

    if isinstance(full, dict):
        ticker = (full.get("ticker") or "").upper()
        exch = (full.get("exchange") or "L").upper()
        return ticker, exch

    parts = (full or "").upper().split(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], "L"


def _close_column(df: pd.DataFrame) -> str | None:
    nm = {c.lower(): c for c in df.columns}
    return nm.get("close_gbp") or nm.get("close") or nm.get("adj close") or nm.get("adj_close")


# A close more than this many calendar days after the wanted date is not a
# usable proxy for it (e.g. the instrument only started trading later).
_MAX_PRICE_GAP_DAYS = 7


def _price_on_or_after(df: pd.DataFrame, date_col: str, price_col: str, target: dt.date) -> float | None:
    mask = (df[date_col] >= target) & (df[date_col] <= target + dt.timedelta(days=_MAX_PRICE_GAP_DAYS))
    if not mask.any():
        return None
    try:
        return float(df.loc[mask, price_col].iloc[0])
    except Exception:
        return None


def _forward_returns(
    ticker: str,
    exchange: str,
    event_date: dt.date,
    horizons: Mapping[str, int] = _HORIZONS,
) -> tuple[Dict[str, float | None], str]:
    """Total returns (price + reinvested dividends) from ``event_date`` per horizon.

    Returns ``(returns, return_basis)``; the basis is ``"price"`` when the
    ticker has no stored corporate actions (see ``total_return_frame``).
    """
    end = event_date + dt.timedelta(days=max(horizons.values()) + _MAX_PRICE_GAP_DAYS)
    df = load_meta_timeseries_range(ticker, exchange, start_date=event_date, end_date=end)
    if df is None or df.empty:
        return {k: None for k in horizons}, PRICE_RETURN_BASIS

    df, basis = total_return_frame(df, ticker, exchange)
    scale = get_scaling_override(ticker, exchange, None)
    df = apply_scaling(df, scale)
    df = df.copy().reset_index()

    nm = {c.lower(): c for c in df.columns}
    date_col = nm.get("date") or nm.get("index") or df.columns[0]
    price_col = _close_column(df)
    if not price_col:
        return {k: None for k in horizons}, basis
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
    df = df.sort_values(date_col)

    base = _price_on_or_after(df, date_col, price_col, event_date)
    if base is not None and not math.isfinite(base):
        base = None

    results: Dict[str, float | None] = {}
    for label, days in horizons.items():
        tgt = event_date + dt.timedelta(days=days)
        end_price = _price_on_or_after(df, date_col, price_col, tgt)
        if end_price is not None and not math.isfinite(end_price):
            end_price = None
        if base is not None and end_price is not None:
            results[label] = end_price / base - 1.0
        else:
            results[label] = None
    return results, basis


def instrument_forward_returns(
    full_ticker: str, event_date: dt.date, horizons: Mapping[str, int]
) -> tuple[Dict[str, float | None], str]:
    """``_forward_returns`` for a ``"SYMBOL.EXCH"`` ticker; ``(returns, return_basis)``."""
    ticker, exchange = _parse_full_ticker(full_ticker)
    return _forward_returns(ticker, exchange, event_date, horizons)


# Below this share of invested value with real price history, a horizon is
# reported as unavailable instead of being extrapolated from the few covered
# holdings.
_MIN_COVERAGE = 0.5

_TickerReturns = tuple[str, tuple[Dict[str, float | None], str]]


def _horizon_return(label: str, own: _TickerReturns, proxy: _TickerReturns) -> tuple[float | None, str | None]:
    """A holding's return for ``label``, falling back to the proxy's; ``None`` when neither has one.

    Also returns the ticker whose price-basis return was used, or ``None``
    when the return used was a total return (or there was none at all).
    """
    for ticker, (returns, basis) in (own, proxy):
        r = returns.get(label)
        if r is not None:
            return r, (ticker if basis == PRICE_RETURN_BASIS else None)
    return None, None


def _holding_returns(
    portfolio: Dict[str, Any],
    event_date: dt.date,
    horizon_days: Mapping[str, int],
    proxy: _TickerReturns,
) -> tuple[list[tuple[float, Dict[str, float | None]]], Dict[str, set[str]]]:
    """Return ``(rows, price_basis)`` for the portfolio's priced holdings.

    ``rows`` holds ``(market_value, {label: return | None})`` per holding. A
    holding's own forward return is used where available, then the proxy
    index's; cash is held flat. ``None`` means neither had prices.
    ``price_basis`` maps each label to the tickers whose return used for it was
    price-only (no stored dividends).
    """

    rows: list[tuple[float, Dict[str, float | None]]] = []
    price_basis: Dict[str, set[str]] = {k: set() for k in horizon_days}
    cache: Dict[str, tuple[Dict[str, float | None], str]] = {}
    for acct in portfolio.get("accounts", []):
        for h in acct.get("holdings", []):
            mv = float(h.get("market_value_gbp") or 0.0)
            if mv == 0.0:
                continue
            full = (h.get("ticker") or "").upper()
            if is_cash_instrument(full, h.get("instrument_type")):
                rows.append((mv, {k: 0.0 for k in horizon_days}))
                continue
            tkr, ex = _parse_full_ticker(full)
            key = f"{tkr}.{ex}"
            if key not in cache:
                cache[key] = _forward_returns(tkr, ex, event_date, horizon_days)
            rets: Dict[str, float | None] = {}
            for label in horizon_days:
                rets[label], source = _horizon_return(label, (key, cache[key]), proxy)
                if source is not None:
                    price_basis[label].add(source)
            rows.append((mv, rets))
    return rows, price_basis


def _shock_horizon(rows: list[tuple[float, Dict[str, float | None]]], label: str) -> tuple[float | None, float]:
    """Return ``(change_in_holdings_value, coverage)`` for one horizon.

    Holdings without any return move with the value-weighted return of those
    that have one, provided at least ``_MIN_COVERAGE`` of the value is covered.
    """

    invested = sum(mv for mv, _ in rows)
    covered = [(mv, rets[label]) for mv, rets in rows if rets[label] is not None]
    covered_mv = sum(mv for mv, _ in covered)
    coverage = covered_mv / invested if invested else 0.0
    if coverage < _MIN_COVERAGE:
        return None, coverage
    covered_return = sum(mv * r for mv, r in covered) / covered_mv
    return invested * covered_return, coverage


def _horizon_basis(delta: float | None, price_tickers: set[str]) -> str | None:
    """``return_basis`` for one horizon; ``None`` when there is no value to describe."""
    if delta is None:
        return None
    return PRICE_RETURN_BASIS if price_tickers else TOTAL_RETURN_BASIS


def apply_historical_event_portfolio(
    portfolio: Dict[str, Any],
    event: Mapping[str, Any] | None,
    *,
    horizons: Mapping[str, int] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Return shocked portfolio valuations for a historical ``event``.

    ``event`` must define ``date`` and ``proxy_index``. ``horizons`` maps a
    result label to a day offset (defaults to ``_HORIZONS``). Each result has
    ``total_value_gbp``, ``delta_gbp``, ``coverage_pct`` (share of invested
    value with real price history), ``return_basis`` (``"total"`` unless some
    return used was price-only; ``None`` when the horizon has no value) and
    ``price_return_tickers`` (those tickers).
    Totals are ``None`` when coverage is too low to say anything, never a
    fabricated number.
    """

    if not event or not event.get("date"):
        raise ValueError("event with a date must be provided")
    horizon_days = dict(horizons or _HORIZONS)

    baseline = float(portfolio.get("total_value_estimate_gbp") or 0.0)
    if baseline == 0.0:
        baseline = sum(float(a.get("value_estimate_gbp") or 0.0) for a in portfolio.get("accounts", []))

    event_date = _parse_date(event["date"])
    proxy: _TickerReturns = ("", ({k: None for k in horizon_days}, TOTAL_RETURN_BASIS))
    if event.get("proxy_index"):
        proxy_tkr, proxy_ex = _parse_full_ticker(event["proxy_index"])
        proxy = (f"{proxy_tkr}.{proxy_ex}", _forward_returns(proxy_tkr, proxy_ex, event_date, horizon_days))

    rows, price_basis = _holding_returns(portfolio, event_date, horizon_days, proxy)
    # Value not represented by a holding (e.g. an account total that includes
    # unlisted items) is carried at baseline, so it never reads as a loss.
    start = baseline or sum(mv for mv, _ in rows)
    result: Dict[str, Dict[str, Any]] = {}
    for label in horizon_days:
        delta, coverage = _shock_horizon(rows, label)
        result[label] = {
            "total_value_gbp": None if delta is None else round(start + delta, 2),
            "delta_gbp": None if delta is None else round(delta, 2),
            "coverage_pct": round(coverage * 100, 1),
            "return_basis": _horizon_basis(delta, price_basis[label]),
            "price_return_tickers": sorted(price_basis[label]),
        }
    return result


def _parse_date(val: Any) -> dt.date:
    """Best-effort conversion of ``val`` to ``date``."""
    if isinstance(val, dt.date):
        return val
    try:
        return dt.datetime.fromisoformat(str(val)).date()
    except Exception:
        raise ValueError(f"Invalid date value: {val!r}")


def _split_ticker(ticker: str) -> tuple[str, str | None]:
    """Split ``"TICKER.EXCH"`` into symbol and exchange."""
    if "." in ticker:
        sym, exch = ticker.rsplit(".", 1)
        return sym, exch.upper()
    return ticker, None


def _get_close(row: pd.Series) -> float | None:
    for col in ("Close_gbp", "Close", "close_gbp", "close"):
        if col in row and pd.notna(row[col]):
            try:
                return float(row[col])
            except Exception:
                return None
    return None


def _last_date(df: pd.DataFrame) -> dt.date | None:
    """The date of ``df``'s last row, or ``None`` when the frame carries no dates.

    Cache frames carry their dates in a ``Date`` column (RangeIndex); older
    callers pass a date index. A frame with neither (a bare numeric index)
    yields ``None`` instead of an integer that cannot be compared to a date.
    """
    columns = {str(col).lower(): col for col in df.columns}
    raw = df[columns["date"]].iloc[-1] if "date" in columns else df.index[-1]
    if not isinstance(raw, (dt.date, str)):
        return None
    ts = pd.to_datetime(raw, errors="coerce")
    return None if pd.isna(ts) else ts.date()


def _calc_return(ticker: str, exchange: str | None, start: dt.date, horizon: int) -> float | None:
    """Calculate the total return (price + reinvested dividends) for ``ticker.exchange`` over ``horizon`` days.

    Price return when the ticker has no stored corporate actions; this
    per-holding map has no field to report the basis in, so callers needing it
    use ``apply_historical_event_portfolio``.
    """
    end = start + dt.timedelta(days=horizon)
    df = load_meta_timeseries_range(ticker, exchange or "", start_date=start, end_date=end)
    if df.empty or len(df) < 2:
        return None

    # Basis deliberately dropped: the fallback is logged by total_return_frame.
    df, _basis = total_return_frame(df, ticker, exchange or "")
    scale = get_scaling_override(ticker, exchange or "", None)
    df = apply_scaling(df, scale)

    # Ensure the data covers (most of) the requested horizon.
    last = _last_date(df)
    if last is None:
        return None
    expected_end = start + dt.timedelta(days=horizon)
    # Allow a few calendar days of tolerance for weekends/holidays.
    if (expected_end - last).days > 3:
        return None

    start_price = _get_close(df.iloc[0])
    end_price = _get_close(df.iloc[-1])
    if not start_price or not end_price:
        return None
    try:
        return (end_price - start_price) / start_price
    except ZeroDivisionError:
        return None


def apply_historical_returns(
    portfolio: Dict[str, Any],
    event: Dict[str, Any] | None = None,
    *,
    event_id: str | None = None,
    date: str | None = None,
    horizons: Iterable[int] | None = None,
) -> Dict[Any, Any]:
    """Apply a historical event to ``portfolio``.

    Returns per-holding forward returns for the requested ``horizons`` in the
    shape ``{ticker: {horizon: return}}``. ``event`` (with ``date`` and
    ``proxy_index``) is required; ``event_id``/``date`` alone are rejected.
    """

    if event is None:
        raise ValueError("event must be provided")

    return apply_historical_event(portfolio, event, horizons=horizons)


def apply_historical_event(
    portfolio: Dict[str, Any],
    event: Dict[str, Any],
    horizons: Iterable[int] | None = None,
) -> Dict[str, Dict[int, float | None]]:
    """Return holding returns for a historical event.

    ``event`` must define ``date`` and ``proxy_index`` (with ``ticker`` and
    ``exchange``). ``horizons`` is an iterable of day offsets. When omitted, the
    function looks for ``horizons`` inside ``event``.

    For each holding, timeseries data is loaded for each horizon. If no data is
    available the return for that horizon falls back to the event's proxy index.
    """

    start = _parse_date(event.get("date"))
    horizons = list(horizons or event.get("horizons") or [5])

    # ``proxy_index`` may be provided either as a dict with ``ticker`` and
    # ``exchange`` keys or as a single string like ``"SPY.N"``.  The previous
    # implementation assumed a mapping which caused an ``AttributeError`` when a
    # string was supplied.  By funnelling the value through
    # ``_parse_full_ticker`` we transparently support both forms and keep the
    # rest of the code agnostic to the input type.
    proxy_val = event.get("proxy_index")
    proxy_ticker, proxy_exchange = (None, None)
    if proxy_val:
        proxy_ticker, proxy_exchange = _parse_full_ticker(proxy_val)

    results: Dict[str, Dict[int, float | None]] = {}

    for acct in portfolio.get("accounts", []):
        for h in acct.get("holdings", []):
            tkr = h.get("ticker") or ""
            sym, exch = _split_ticker(tkr)
            ret_map: Dict[int, float | None] = {}
            for hz in horizons:
                ret = _calc_return(sym, exch, start, hz)
                if ret is None and proxy_ticker:
                    ret = _calc_return(proxy_ticker, proxy_exchange, start, hz)
                ret_map[hz] = ret
            results[tkr] = ret_map

    return results
