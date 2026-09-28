"""Rebuild an account's holdings document from its transactions.

Positions are replayed through a UK Section 104 average-cost pool per
instrument: acquisitions add units and their allowable cost, disposals remove
cost pro rata.  The rebuilt document is then merged with the account's
existing holdings so that information the transactions cannot reproduce
(``value_gbp``, names, a cost basis for units whose cost is unknown, other
hand-maintained fields) is carried forward instead of discarded.

Cash
----
``DEPOSIT``/``WITHDRAWAL``/``DIVIDEND``/``INTEREST`` rows and ``CASH.GBP``
transfers always move ``CASH.GBP``.  Trade settlements (``BUY``/``SELL``) and
charges (``FEES``/``FEES_REFUND``/``INTEREST_CHARGE``) move it only when the
transactions document opts in with ``"trade_cash_effects": true``; accounts
whose cash balance was reconciled without them keep their existing behaviour.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

CASH_TICKER = "CASH.GBP"
TRADE_CASH_FLAG = "trade_cash_effects"

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ACQUIRE = {"BUY", "PURCHASE", "TRANSFER_IN"}
_DISPOSE = {"SELL", "TRANSFER_OUT", "REMOVAL"}
_SETTLED_TRADES = {"BUY": -1, "PURCHASE": -1, "SELL": 1}
_CASH_FLOWS = {"DEPOSIT": 1, "WITHDRAWAL": -1, "DIVIDEND": 1, "DIVIDENDS": 1, "INTEREST": 1}
_CHARGES = {"FEES": -1, "FEES_REFUND": 1, "INTEREST_CHARGE": -1}
_SHARE_SCALE = 10**8
_EPS = 1e-9


@dataclass
class Position:
    """Section 104 pool for one instrument."""

    units: float = 0.0
    cost: float = 0.0
    unknown_cost_units: float = 0.0
    acquired_date: str | None = None

    def acquire(self, qty: float, cost: float | None, tx_date: str) -> None:
        self.units += qty
        if cost is None:
            self.unknown_cost_units += qty
        else:
            self.cost += cost
        if _ISO_DATE_RE.match(tx_date) and (self.acquired_date is None or tx_date > self.acquired_date):
            self.acquired_date = tx_date

    def dispose(self, qty: float) -> float:
        """Remove ``qty`` units; return how many were not in the pool."""
        matched = min(qty, self.units)
        fraction = matched / self.units if self.units > _EPS else 0.0
        self.units -= matched
        self.cost -= self.cost * fraction
        self.unknown_cost_units -= self.unknown_cost_units * fraction
        if self.units <= _EPS:
            self.units = self.cost = self.unknown_cost_units = 0.0
        return qty - matched

    @property
    def cost_known(self) -> bool:
        return self.unknown_cost_units <= _EPS


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if result != result else result  # NaN check


def _quantity(tx: Mapping[str, Any]) -> float | None:
    for key in ("shares", "quantity", "units"):
        if tx.get(key) is not None:
            qty = _float(tx[key])
            if qty is None:
                return None
            qty = abs(qty)
            return qty / _SHARE_SCALE if qty > 1_000_000 else qty  # PP's 1e8 scaling
    return None


def _settled_value(tx: Mapping[str, Any], qty: float, *, acquisition: bool) -> float | None:
    """Settled GBP value: ``amount_minor`` if non-zero, else price x units +/- fees.

    A zero ``amount_minor`` (common on transfers-in) records no value, so it is
    treated as unknown rather than as a known cost of nothing.
    """
    amount_minor = _float(tx.get("amount_minor"))
    if amount_minor:
        return abs(amount_minor) / 100.0
    price = _float(tx.get("price_gbp"))
    if price is None:
        return None
    fees = _float(tx.get("fees")) or 0.0
    return price * qty + fees if acquisition else price * qty - fees


def _name(record: Mapping[str, Any]) -> str | None:
    for key in ("instrument_name", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _name_aliases(transactions: Sequence[Mapping[str, Any]], existing: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Map instrument names to tickers so ticker-less trades join the right pool."""
    aliases: dict[str, str] = {}
    for record in [*existing, *transactions]:
        ticker = str(record.get("ticker") or "").strip().upper()
        name = _name(record)
        if ticker and name:
            aliases.setdefault(name, ticker)
    return aliases


def _instrument_key(tx: Mapping[str, Any], aliases: Mapping[str, str]) -> str | None:
    ticker = str(tx.get("ticker") or "").strip().upper()
    if ticker:
        return ticker
    name = _name(tx)
    if name is None:
        return None
    return aliases.get(name, f"name:{name}")


def _sort_key(indexed: tuple[int, Mapping[str, Any]]) -> tuple[int, str, int, int]:
    """Dated rows by date (acquisitions first); undated rows last, in file order."""
    idx, tx = indexed
    tx_type = str(tx.get("type") or "").upper()
    day = str(tx.get("date") or "")[:10]
    if not _ISO_DATE_RE.match(day):
        return (1, "", 0, idx)
    return (0, day, 0 if tx_type in _ACQUIRE else 1, idx)


@dataclass
class Replay:
    """Result of replaying a transactions list."""

    positions: dict[str, Position]
    cash: float = 0.0
    cash_seen: bool = False


def _apply_trade(replay: Replay, tx: Mapping[str, Any], tx_type: str, key: str, trade_cash: bool) -> None:
    qty = _quantity(tx)
    if not qty:
        logger.warning(
            "Skipping %s with no usable quantity for %s", sanitise_log_value(tx_type), sanitise_log_value(key)
        )
        return
    if key == CASH_TICKER:
        replay.cash += qty if tx_type in _ACQUIRE else -qty
        replay.cash_seen = True
        return
    position = replay.positions.setdefault(key, Position())
    acquisition = tx_type in _ACQUIRE
    value = _settled_value(tx, qty, acquisition=acquisition)
    if acquisition:
        position.acquire(qty, value, str(tx.get("date") or "")[:10])
    else:
        unmatched = position.dispose(qty)
        if unmatched > _EPS:
            logger.warning(
                "%s of %s %s exceeds units held; ignoring the excess",
                sanitise_log_value(tx_type),
                sanitise_log_value(qty),
                sanitise_log_value(key),
            )
    if trade_cash and tx_type in _SETTLED_TRADES and value is not None:
        replay.cash += value * _SETTLED_TRADES[tx_type]
        replay.cash_seen = True


def _apply_cash(replay: Replay, tx: Mapping[str, Any], sign: int) -> None:
    amount_minor = _float(tx.get("amount_minor"))
    if amount_minor is None:
        logger.warning("Skipping %s with unparseable amount_minor", sanitise_log_value(tx.get("type")))
        return
    replay.cash += (abs(amount_minor) / 100.0) * sign
    replay.cash_seen = True


def replay_transactions(
    transactions: Sequence[Mapping[str, Any]],
    *,
    trade_cash: bool = False,
    aliases: Mapping[str, str] | None = None,
) -> Replay:
    """Replay ``transactions`` in date order (acquisitions first within a day, undated last)."""
    replay = Replay(positions={})
    aliases = aliases or {}
    cash_signs = {**_CASH_FLOWS, **(_CHARGES if trade_cash else {})}
    for _, tx in sorted(enumerate(transactions), key=_sort_key):
        tx_type = str(tx.get("type") or "").upper()
        if tx_type in _ACQUIRE or tx_type in _DISPOSE:
            key = _instrument_key(tx, aliases)
            if key is None:
                logger.warning("Skipping %s with neither ticker nor instrument_name", sanitise_log_value(tx_type))
                continue
            _apply_trade(replay, tx, tx_type, key, trade_cash)
        elif tx_type in cash_signs:
            _apply_cash(replay, tx, cash_signs[tx_type])
    return replay


def _units_match(a: Any, b: float) -> bool:
    value = _float(a)
    return value is not None and abs(value - b) < 1e-6


def _cost_basis(position: Position, previous: Mapping[str, Any] | None) -> float:
    """Pool cost if fully known; else the previous cost for unchanged units; else 0 (derive later)."""
    if position.cost_known:
        return round(position.cost, 2)
    if previous is not None and _units_match(previous.get("units"), position.units):
        previous_cost = _float(previous.get("cost_basis_gbp"))
        if previous_cost is not None:
            return previous_cost
    return 0.0


def _merge_holding(
    ticker: str, units: float, cost: float, acquired: str | None, previous: Mapping[str, Any] | None
) -> dict[str, Any]:
    holding: dict[str, Any] = dict(previous) if previous else {}
    old_units = _float(holding.get("units"))
    old_value = _float(holding.get("value_gbp"))
    holding.update({"ticker": ticker, "units": units, "cost_basis_gbp": cost})
    if acquired:
        holding["acquired_date"] = acquired
    if ticker == CASH_TICKER:
        if "value_gbp" in holding:
            holding["value_gbp"] = units
    elif old_value is not None and old_units and not _units_match(old_units, units):
        # Revalue at the last known price until the pricing pipeline refreshes it.
        holding["value_gbp"] = round(old_value / old_units * units, 2)
    return holding


def _computed_holdings(replay: Replay, previous: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, position in replay.positions.items():
        if position.units <= _EPS:
            continue
        if key.startswith("name:"):
            logger.warning("No ticker known for %s; position left out of holdings", sanitise_log_value(key[5:]))
            continue
        prev = previous.get(key)
        units = round(position.units, 8)
        out[key] = _merge_holding(key, units, _cost_basis(position, prev), position.acquired_date, prev)
    cash = round(replay.cash, 2)
    if replay.cash_seen and abs(cash) >= 0.005:
        out[CASH_TICKER] = _merge_holding(CASH_TICKER, cash, cash, None, previous.get(CASH_TICKER))
    return out


def rebuild_holdings_document(
    tx_data: Mapping[str, Any],
    owner: str,
    account: str,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the rebuilt holdings document, carrying forward ``existing`` data."""
    transactions = [t for t in tx_data.get("transactions") or [] if isinstance(t, Mapping)]
    existing = existing if isinstance(existing, Mapping) else {}
    old_holdings = [h for h in existing.get("holdings") or [] if isinstance(h, Mapping)]
    previous = {str(h.get("ticker") or "").upper(): h for h in old_holdings if h.get("ticker")}

    replay = replay_transactions(
        transactions,
        trade_cash=tx_data.get(TRADE_CASH_FLAG) is True,
        aliases=_name_aliases(transactions, old_holdings),
    )
    computed = _computed_holdings(replay, previous)
    # Keep the existing ordering so the rewritten file diffs cleanly.
    ordered = [computed.pop(t) for t in previous if t in computed]
    ordered.extend(computed.values())

    doc: dict[str, Any] = dict(existing)
    doc.update(
        {
            "owner": owner,
            "account_type": account.upper(),
            "currency": str(tx_data.get("currency") or existing.get("currency") or "GBP"),
            "last_updated": date.today().isoformat(),
            "holdings": ordered,
        }
    )
    return doc
