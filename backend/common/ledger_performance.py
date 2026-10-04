"""Cash-flow-aware portfolio returns reconstructed from the transaction ledger.

Why this module exists
----------------------
``portfolio_utils.compute_owner_performance`` and ``_portfolio_value_series``
(and therefore ``compute_time_weighted_return`` and ``compute_xirr``, which are
built on the latter) value the owner's *current* holdings at historical
prices. That is the return today's basket would have earned, not the return
the portfolio actually earned: trades are ignored, history stops at a fixed
``days`` window so there is no since-inception figure, and the TWR's flow
adjustment subtracts deposits and dividends from a value series that never
received them (so a deposit reads as a loss and dividends reduce the return).

This module instead replays each account's ledger through
:func:`backend.common.holdings_rebuild.replay_transactions` -- the same
Section 104 replay the holdings rebuild uses -- to get the units and cash
actually held on every business day, values them at that day's GBP close, and
chains daily sub-period returns around external flows (flows at the start of
the day)::

    r_d = (V_d + I_d) / (V_{d-1} + F_d) - 1

``F`` is external money: deposits, withdrawals and transfers in/out
(securities valued at that day's price). Dividends and interest land in cash
and stay in ``V``, so they count as return rather than as flows.

An account whose ledger does not record trade settlements in cash (no
``trade_cash_effects`` flag, see ``holdings_rebuild``) cannot reproduce a cash
balance. For such an account cash is left out of ``V``, buys/sells are treated
as external flows and income is paid out through ``I``, i.e. a
securities-plus-income return.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, Mapping, Sequence, TypeVar, cast

import numpy as np
import pandas as pd

from backend.common import holdings_rebuild
from backend.common.data_loader import resolve_paths
from backend.common.holdings_rebuild import (
    CASH_TICKER,
    TRADE_CASH_FLAG,
    _instrument_key,
    _quantity,
    _settled_value,
    name_aliases,
    replay_transactions,
)
from backend.common.path_utils import safe_join
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
# Below this many observations an annualised volatility/Sharpe is noise.
MIN_OBSERVATIONS_FOR_RISK = 20
# A day whose opening capital (V_{d-1} + F_d) is below this has no meaningful
# return (e.g. an account funded by a buy before any deposit is recorded).
_MIN_CAPITAL_GBP = 1.0

_EXTERNAL_CASH = {"DEPOSIT": 1, "WITHDRAWAL": -1}
_INCOME = {"DIVIDEND", "DIVIDENDS", "INTEREST"}
_TRADES = {"BUY": 1, "PURCHASE": 1, "SELL": -1}
_TRANSFERS = {"TRANSFER_IN": 1, "TRANSFER_OUT": -1}
# REMOVAL takes units out with no proceeds (a write-off), so it is a loss,
# not an external flow.
_UNIT_ONLY = {"REMOVAL"}

PriceLoader = Callable[[str, date, date], pd.Series]


@dataclass(frozen=True)
class AccountLedger:
    """One account's transactions plus whether trades settle through its cash."""

    account: str
    transactions: Sequence[Mapping[str, Any]]
    trade_cash: bool


@dataclass(frozen=True)
class LedgerPerformance:
    """Daily valuation and chained returns rebuilt from the ledger.

    Every series/frame is indexed by business day (``DatetimeIndex``) from the
    first ledger activity to the reporting ``end``.
    """

    inception: date
    end: date
    values: pd.Series
    returns: pd.Series
    denominators: pd.Series
    cash: pd.Series
    instrument_values: pd.DataFrame
    instrument_pnl: pd.DataFrame
    names: Mapping[str, str] = field(default_factory=dict)
    unpriced: tuple[str, ...] = ()
    # External money in (+) / out (-) at the start of each day, and income
    # paid out of accounts whose cash is not tracked (see the module docstring).
    flows: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    income: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


@dataclass
class _Events:
    """Per-day ledger events that are not visible in the replayed positions."""

    external: defaultdict[pd.Timestamp, float] = field(default_factory=lambda: defaultdict(float))
    income: defaultdict[pd.Timestamp, float] = field(default_factory=lambda: defaultdict(float))
    trade_flows: defaultdict[tuple[str, pd.Timestamp], float] = field(default_factory=lambda: defaultdict(float))
    transfer_units: defaultdict[tuple[str, pd.Timestamp], float] = field(default_factory=lambda: defaultdict(float))
    attributed_income: defaultdict[tuple[str, pd.Timestamp], float] = field(default_factory=lambda: defaultdict(float))
    implied_prices: dict[tuple[str, pd.Timestamp], float] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)


def load_owner_ledgers(owner: str) -> list[AccountLedger]:
    """Read ``<accounts_root>/<owner>/*_transactions.json``, one ledger per account.

    These are the documents the holdings rebuild replays (and that
    ``account_scaffold.load_transactions`` reads), so the history rebuilt here
    reproduces the stored holdings. Exports under ``<data_root>/transactions``
    are deliberately not read: they can be older copies of the same accounts.
    Returns ``[]`` when the owner has no account directory.
    """
    root = resolve_paths(config.repo_root, config.accounts_root).accounts_root
    try:
        owner_dir = safe_join(root, owner)
    except ValueError:
        return []
    ledgers: list[AccountLedger] = []
    for path in sorted(owner_dir.glob("*_transactions.json")) if owner_dir.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping unreadable ledger %s: %s", sanitise_log_value(path), sanitise_log_value(exc))
            continue
        if not isinstance(data, dict):
            continue
        transactions = [tx for tx in data.get("transactions") or [] if isinstance(tx, dict)]
        account = path.name.removesuffix("_transactions.json")
        ledgers.append(AccountLedger(account, transactions, data.get(TRADE_CASH_FLAG) is True))
    return ledgers


# ──────────────────────────────────────────────────────────────
# Prices
# ──────────────────────────────────────────────────────────────
def _resolve_symbol(key: str) -> tuple[str, str] | None:
    if key.startswith(("name:", "ref:")):
        return None
    from backend.common import instrument_api, portfolio_utils

    # The resolver only looks at the snapshot's keys.
    snapshot = cast(Dict[str, float], portfolio_utils._PRICE_SNAPSHOT)
    return instrument_api._resolve_full_ticker(key, snapshot)


def load_gbp_closes(key: str, start: date, end: date) -> pd.Series:
    """Daily GBP closes for instrument ``key`` between ``start`` and ``end``.

    Mirrors ``holding_utils._get_price_for_date_scaled``: prefer the
    FX-converted ``Close_gbp`` column (never scaled), else ``Close`` with the
    instrument's scaling override (e.g. GBX pence -> pounds).
    """
    from backend.timeseries.cache import load_meta_timeseries_range
    from backend.utils.timeseries_helpers import get_scaling_override

    resolved = _resolve_symbol(key)
    if resolved is None:
        return pd.Series(dtype=float)
    symbol, exchange = resolved
    df = load_meta_timeseries_range(symbol, exchange, start, end)
    if df is None or df.empty or "Date" not in df.columns:
        return pd.Series(dtype=float)
    columns = {str(column).lower(): column for column in df.columns}
    scale = 1.0
    column = columns.get("close_gbp")
    if column is None:
        column = columns.get("close")
        scale = get_scaling_override(symbol, exchange, None) or 1.0
    if column is None:
        return pd.Series(dtype=float)
    closes = pd.to_numeric(df[column], errors="coerce") * scale
    closes.index = pd.DatetimeIndex(pd.to_datetime(df["Date"])).normalize()
    closes = closes.dropna()
    return closes[~closes.index.duplicated(keep="last")].sort_index()


def _price_column(key: str, index: pd.DatetimeIndex, implied: pd.Series, loader: PriceLoader) -> tuple[pd.Series, bool]:
    """Price ``key`` on every day of ``index``; return ``(prices, has_market_prices)``.

    Market closes are carried forward over gaps. Days before the first close
    (or every day, for an instrument with no price history) fall back to the
    price implied by its trades, so a position never jumps from zero to its
    market value and fakes a return.
    """
    try:
        market = loader(key, index[0].date(), index[-1].date())
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("No price history for %s: %s", sanitise_log_value(key), sanitise_log_value(exc))
        market = pd.Series(dtype=float)
    on_index = pd.Series(float("nan"), index=index)
    if not market.empty:
        union = index.union(pd.DatetimeIndex(market.index))
        on_index = market.reindex(union).ffill().reindex(index)
    filled = on_index.fillna(implied.reindex(index).ffill()).bfill()
    return filled.fillna(0.0), not market.empty


# ──────────────────────────────────────────────────────────────
# Ledger replay
# ──────────────────────────────────────────────────────────────
def _parse_day(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw or "")[:10])
    except ValueError:
        return None


def _business_day(day: date, last: pd.Timestamp) -> pd.Timestamp:
    """Roll a weekend date forward to Monday, but never past the last index day."""
    stamp = pd.Timestamp(day)
    while stamp.weekday() >= 5:
        stamp += pd.Timedelta(days=1)
    return min(stamp, last)


def _dated_rows(ledger: AccountLedger, end: date) -> list[tuple[date, Mapping[str, Any]]]:
    rows: list[tuple[date, Mapping[str, Any]]] = []
    for tx in ledger.transactions:
        day = _parse_day(tx.get("date"))
        if day is not None and day <= end:
            rows.append((day, tx))
    return rows


def _positions(
    ledger: AccountLedger,
    rows: Sequence[tuple[date, Mapping[str, Any]]],
    aliases: Mapping[str, str],
    index: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, pd.Series]:
    """Units per instrument and cash at the close of every business day.

    Replays the ledger prefix up to each day that has activity, so the units
    follow exactly the rules the holdings rebuild applies (aliases, pooled
    disposals capped at units held, acquisitions first within a day).
    """
    by_day: dict[pd.Timestamp, list[Mapping[str, Any]]] = defaultdict(list)
    for day, tx in rows:
        by_day[_business_day(day, index[-1])].append(tx)
    units: dict[pd.Timestamp, dict[str, float]] = {}
    cash: dict[pd.Timestamp, float] = {}
    prefix: list[Mapping[str, Any]] = []
    for day in sorted(by_day):
        prefix.extend(by_day[day])
        replay = replay_transactions(prefix, trade_cash=ledger.trade_cash, aliases=aliases, warn=False)
        units[day] = {key: pos.units for key, pos in replay.positions.items()}
        cash[day] = replay.cash if ledger.trade_cash else 0.0
    unit_frame = pd.DataFrame.from_dict(units, orient="index").sort_index()
    unit_frame = unit_frame.reindex(index).ffill().fillna(0.0)
    cash_series = pd.Series(cash, dtype=float).sort_index().reindex(index).ffill().fillna(0.0)
    return unit_frame, cash_series


def _record_instrument_event(
    events: _Events, ledger: AccountLedger, day: pd.Timestamp, tx: Mapping[str, Any], key: str
) -> None:
    tx_type = str(tx.get("type") or "").upper()
    qty = _quantity(tx)
    if not qty:
        return
    if key == CASH_TICKER:
        # Cash moved in or out of the account from outside it.
        if tx_type in _TRANSFERS and ledger.trade_cash:
            events.external[day] += _TRANSFERS[tx_type] * qty
        return
    name = holdings_rebuild._name(tx)
    if name:
        events.names.setdefault(key, name.title())
    if tx_type in _TRANSFERS:
        events.transfer_units[(key, day)] += _TRANSFERS[tx_type] * qty
        return
    if tx_type in _UNIT_ONLY:
        return
    sign = _TRADES[tx_type]
    value = _settled_value(tx, qty, acquisition=sign > 0)
    if value is None:
        return
    events.implied_prices[(key, day)] = value / qty
    events.trade_flows[(key, day)] += sign * value
    if not ledger.trade_cash:
        events.external[day] += sign * value


def _record_event(
    events: _Events,
    ledger: AccountLedger,
    day: pd.Timestamp,
    tx: Mapping[str, Any],
    aliases: Mapping[str, str],
) -> None:
    tx_type = str(tx.get("type") or "").upper()
    if tx_type in _TRADES or tx_type in _TRANSFERS or tx_type in _UNIT_ONLY:
        key = _instrument_key(tx, aliases)
        if key is not None:
            _record_instrument_event(events, ledger, day, tx, key)
        return
    try:
        amount = abs(float(tx.get("amount_minor") or 0.0)) / 100.0
    except (TypeError, ValueError):
        return
    if tx_type in _EXTERNAL_CASH and ledger.trade_cash:
        events.external[day] += _EXTERNAL_CASH[tx_type] * amount
    elif tx_type in _INCOME:
        if not ledger.trade_cash:
            events.income[day] += amount
        key = _instrument_key(tx, aliases)
        if key is not None and key != CASH_TICKER:
            events.attributed_income[(key, day)] += amount


def _keyed_frame(values: Mapping[tuple[str, pd.Timestamp], float], index: pd.DatetimeIndex) -> pd.DataFrame:
    """Day x instrument frame from already-summed ``{(key, day): value}``; missing cells are 0."""
    columns: dict[str, dict[pd.Timestamp, float]] = defaultdict(dict)
    for (key, day), value in values.items():
        columns[key][day] = value
    return pd.DataFrame(columns, index=index, dtype=float).fillna(0.0)


def _daily(values: Mapping[pd.Timestamp, float], index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(dict(values), dtype=float).reindex(index, fill_value=0.0)


# ──────────────────────────────────────────────────────────────
# Assembly
# ──────────────────────────────────────────────────────────────
def _replay_accounts(
    ledgers: Sequence[AccountLedger],
    end: date,
    aliases: Mapping[str, str],
) -> tuple[pd.DatetimeIndex, pd.DataFrame, pd.Series, _Events] | None:
    dated = [(ledger, _dated_rows(ledger, end)) for ledger in ledgers]
    days = [day for _, rows in dated for day, _ in rows]
    if not days:
        return None
    index = pd.bdate_range(min(days), end)
    if index.empty:
        return None
    units = pd.DataFrame(index=index, dtype=float)
    cash = pd.Series(0.0, index=index)
    events = _Events()
    for ledger, rows in dated:
        if not rows:
            continue
        account_units, account_cash = _positions(ledger, rows, aliases, index)
        units = units.add(account_units, fill_value=0.0)
        cash = cash.add(account_cash, fill_value=0.0)
        for day, tx in rows:
            _record_event(events, ledger, _business_day(day, index[-1]), tx, aliases)
    return index, units.fillna(0.0), cash, events


def _value_instruments(
    units: pd.DataFrame, events: _Events, loader: PriceLoader
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    """Return ``(prices, values, unpriced_keys)`` for every replayed instrument."""
    index = pd.DatetimeIndex(units.index)
    implied = _keyed_frame(events.implied_prices, index).replace(0.0, float("nan"))
    prices = pd.DataFrame(index=index, dtype=float)
    unpriced: list[str] = []
    for key in units.columns:
        implied_key = implied[key] if key in implied.columns else pd.Series(dtype=float)
        prices[key], has_market = _price_column(key, index, implied_key, loader)
        if not has_market and units[key].abs().sum() > 0:
            unpriced.append(key)
    return prices, units * prices, tuple(sorted(unpriced))


def _chain_returns(values: pd.Series, flows: pd.Series, income: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Daily TWR sub-period returns with start-of-day flows; also the denominators."""
    denominators = values.shift(1, fill_value=0.0) + flows
    capital = denominators.where(denominators > _MIN_CAPITAL_GBP)
    returns = ((values + income) / capital - 1.0).fillna(0.0)
    return returns, denominators


def build_ledger_performance(
    ledgers: Sequence[AccountLedger],
    end: date,
    *,
    holdings: Iterable[Mapping[str, Any]] = (),
    price_loader: PriceLoader | None = None,
) -> LedgerPerformance | None:
    """Rebuild daily values and returns from ``ledgers`` up to ``end``.

    ``holdings`` (current holding records) only contribute instrument-name
    aliases so ticker-less trades join the right pool, as in the rebuild.
    Returns ``None`` when no dated transaction falls on or before ``end``.
    """
    all_txs = [tx for ledger in ledgers for tx in ledger.transactions]
    aliases = name_aliases(all_txs, list(holdings))
    replayed = _replay_accounts(ledgers, end, aliases)
    if replayed is None:
        return None
    index, units, cash, events = replayed
    prices, instrument_values, unpriced = _value_instruments(units, events, price_loader or load_gbp_closes)
    transfer_flows = _keyed_frame(events.transfer_units, index).reindex(columns=prices.columns, fill_value=0.0)
    transfer_flows = transfer_flows.fillna(0.0) * prices
    values = instrument_values.sum(axis=1) + cash
    flows = _daily(events.external, index) + transfer_flows.sum(axis=1)
    paid_out = _daily(events.income, index)
    returns, denominators = _chain_returns(values, flows, paid_out)
    trade_flows = _keyed_frame(events.trade_flows, index).reindex(columns=prices.columns, fill_value=0.0)
    income = _keyed_frame(events.attributed_income, index).reindex(columns=prices.columns, fill_value=0.0)
    pnl = (
        instrument_values.diff().fillna(instrument_values)
        - trade_flows.fillna(0.0)
        - transfer_flows
        + income.fillna(0.0)
    )
    return LedgerPerformance(
        inception=index[0].date(),
        end=end,
        values=values,
        returns=returns,
        denominators=denominators,
        cash=cash,
        instrument_values=instrument_values,
        instrument_pnl=pnl,
        names=dict(events.names),
        unpriced=unpriced,
        flows=flows,
        income=paid_out,
    )


def unreconciled_instruments(
    ledgers: Sequence[AccountLedger], holdings: Iterable[Mapping[str, Any]]
) -> tuple[str, ...]:
    """Current non-cash holdings whose units the full ledger does not reproduce.

    Such holdings (typically entered by hand, or imported as a snapshot) are
    missing from the rebuilt history, so returns would exclude them.
    """
    holding_list = list(holdings)
    held: dict[str, float] = defaultdict(float)
    for holding in holding_list:
        ticker = str(holding.get("ticker") or "").upper()
        if ticker and not ticker.startswith("CASH"):
            try:
                held[ticker] += float(holding.get("units") or 0.0)
            except (TypeError, ValueError):
                continue
    all_txs = [tx for ledger in ledgers for tx in ledger.transactions]
    aliases = name_aliases(all_txs, holding_list)
    replayed: dict[str, float] = defaultdict(float)
    for ledger in ledgers:
        replay = replay_transactions(ledger.transactions, trade_cash=ledger.trade_cash, aliases=aliases, warn=False)
        for key, position in replay.positions.items():
            replayed[key] += position.units
    return tuple(sorted(key for key, units in held.items() if abs(replayed.get(key, 0.0) - units) > 1e-6))


# ──────────────────────────────────────────────────────────────
# Period maths over the chained daily returns
# ──────────────────────────────────────────────────────────────
_Indexed = TypeVar("_Indexed", pd.Series, pd.DataFrame)


def _window(data: _Indexed, after: date | None, through: date) -> _Indexed:
    """Rows dated in ``(after, through]`` (``after=None``: everything up to ``through``)."""
    mask = data.index <= pd.Timestamp(through)
    if after is not None:
        mask &= data.index > pd.Timestamp(after)
    return data.loc[mask]


def _floats(series: pd.Series) -> np.ndarray:
    return series.to_numpy(dtype=float)


def chained_return(returns: pd.Series, after: date | None, through: date) -> float | None:
    """Geometrically chained return for days in ``(after, through]``; ``None`` if no days."""
    window = _floats(_window(returns, after, through))
    if window.size == 0:
        return None
    return float(np.prod(1.0 + window) - 1.0)


def annualise(total: float | None, days: int) -> float | None:
    """Annualise a cumulative return over ``days`` calendar days (``None`` under a year)."""
    if total is None or days < 365 or total <= -1.0:
        return None
    return float((1.0 + total) ** (365.25 / days) - 1.0)


def annualised_volatility(returns: pd.Series, after: date | None, through: date) -> float | None:
    window = _floats(_window(returns, after, through))
    if window.size < MIN_OBSERVATIONS_FOR_RISK:
        return None
    std = float(np.std(window, ddof=1))
    return std * math.sqrt(TRADING_DAYS_PER_YEAR) if math.isfinite(std) else None


def sharpe_ratio(returns: pd.Series, after: date | None, through: date, risk_free_rate: float) -> float | None:
    """Annualised excess return over annualised volatility for days in ``(after, through]``."""
    window = _floats(_window(returns, after, through))
    volatility = annualised_volatility(returns, after, through)
    if not volatility:
        return None
    growth = float(np.prod(1.0 + window))
    if growth <= 0:
        return None
    annual = growth ** (TRADING_DAYS_PER_YEAR / window.size) - 1.0
    return (annual - risk_free_rate) / volatility


@dataclass(frozen=True)
class Drawdown:
    max_drawdown: float
    peak: date
    trough: date
    current_drawdown: float
    current_peak: date


def drawdown(returns: pd.Series, after: date | None, through: date) -> Drawdown | None:
    """Drawdowns of the TWR wealth index (so deposits/withdrawals never look like moves)."""
    selected = _window(returns, after, through)
    if selected.empty:
        return None
    days = pd.DatetimeIndex(selected.index)
    wealth = np.cumprod(1.0 + _floats(selected))
    depth = wealth / np.maximum.accumulate(wealth) - 1.0
    trough = int(np.argmin(depth))
    # argmax returns the first occurrence, i.e. the day the peak was set.
    peak = int(np.argmax(wealth[: trough + 1]))
    return Drawdown(
        max_drawdown=float(depth[trough]),
        peak=days[peak].date(),
        trough=days[trough].date(),
        current_drawdown=float(depth[-1]),
        current_peak=days[int(np.argmax(wealth))].date(),
    )


def contributions(perf: LedgerPerformance, after: date | None, through: date) -> pd.DataFrame:
    """Per-instrument GBP P&L and contribution to return for days in ``(after, through]``.

    ``contribution`` sums each day's P&L over that day's opening capital, so the
    contributions add up to the arithmetic sum of the daily returns (not the
    chained return; the difference is the compounding cross-term).
    """
    pnl = _window(perf.instrument_pnl, after, through)
    if pnl.empty:
        return pd.DataFrame(columns=["pnl_gbp", "contribution"])
    capital = _window(perf.denominators, after, through)
    capital = capital.where(capital > _MIN_CAPITAL_GBP)
    contribution = pnl.div(capital, axis=0).fillna(0.0).sum()
    return pd.DataFrame({"pnl_gbp": pnl.sum(), "contribution": contribution})


def weights_at(perf: LedgerPerformance, through: date) -> tuple[dict[str, float], float] | None:
    """Instrument weights and cash weight of total value at the last day on or before ``through``."""
    values = _window(perf.values, None, through)
    if values.empty:
        return None
    total = float(_floats(values)[-1])
    if total <= 0:
        return None
    position = len(values) - 1
    holdings = perf.instrument_values.iloc[position]
    amounts = holdings.to_numpy(dtype=float)
    weights = {str(key): amount / total for key, amount in zip(holdings.index, amounts) if amount > 0}
    return weights, float(_floats(perf.cash)[position]) / total


def close_on_or_before(closes: pd.Series, day: date) -> float | None:
    window = _floats(_window(closes, None, day))
    if window.size == 0:
        return None
    return float(window[-1])


def price_return(closes: pd.Series, after: date, through: date) -> float | None:
    """Close-to-close return between the last closes on or before ``after`` and ``through``."""
    start = close_on_or_before(closes, after)
    finish = close_on_or_before(closes, through)
    if start is None or finish is None or start <= 0:
        return None
    return finish / start - 1.0


def one_year_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def last_complete_month_end(today: date) -> date:
    return today.replace(day=1) - timedelta(days=1)
