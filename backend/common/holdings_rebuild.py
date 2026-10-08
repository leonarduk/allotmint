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
from typing import Any, Callable, Mapping, Sequence

from backend.common.ticker_utils import canonical_ticker
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
    unknown_cost_since: str | None = None

    def acquire(self, qty: float, cost: float | None, tx_date: str) -> None:
        self.units += qty
        if cost is None:
            self.unknown_cost_units += qty
            if _ISO_DATE_RE.match(tx_date) and (self.unknown_cost_since is None or tx_date < self.unknown_cost_since):
                self.unknown_cost_since = tx_date
        else:
            self.cost += cost
        if _ISO_DATE_RE.match(tx_date) and (self.acquired_date is None or tx_date > self.acquired_date):
            self.acquired_date = tx_date

    def dispose(self, qty: float) -> tuple[float, float, float]:
        """Remove ``qty`` units pro rata.

        Returns ``(cost, unknown_cost_units, unmatched)``: the allowable cost
        taken out, how many of the units taken had no known cost, and how many
        of ``qty`` were not in the pool at all.
        """
        matched = min(qty, self.units)
        fraction = matched / self.units if self.units > _EPS else 0.0
        cost_out = self.cost * fraction
        unknown_out = self.unknown_cost_units * fraction
        self.units -= matched
        self.cost -= cost_out
        self.unknown_cost_units -= unknown_out
        if self.units <= _EPS:
            self.units = self.cost = self.unknown_cost_units = 0.0
        return cost_out, unknown_out, qty - matched

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


# Quantity fields in precedence order, with the divisor that turns each into
# real units.  ``units`` and ``quantity`` hold real units.  ``shares`` is
# Portfolio Performance's fixed-point share count (real units x 10^8), as
# written by ``convert_portfolio_xml_to_account_transactions``.  ``units`` wins
# so that a PP row edited in the app (which sets ``units``) uses the edit.
_QUANTITY_FIELDS = (("units", 1), ("quantity", 1), ("shares", _SHARE_SCALE))


def transaction_quantity(tx: Mapping[str, Any]) -> float | None:
    """Signed number of real units ``tx`` records, or ``None`` if unknown.

    Scale is decided by which field is present (see ``_QUANTITY_FIELDS``),
    never by the size of the value: 2,000,000 ``units`` is 2,000,000 units and
    999,999 ``shares`` is 0.00999999 units.  The first field that is present
    decides; an unparseable value there makes the quantity unknown.
    """
    for key, scale in _QUANTITY_FIELDS:
        if tx.get(key) is not None:
            qty = _float(tx[key])
            return None if qty is None else qty / scale
    return None


def _quantity(tx: Mapping[str, Any]) -> float | None:
    qty = transaction_quantity(tx)
    return None if qty is None else abs(qty)


def _priced_value(tx: Mapping[str, Any], qty: float, *, acquisition: bool) -> float | None:
    """Price x units, plus fees on an acquisition or minus them on a disposal."""
    price = _float(tx.get("price_gbp"))
    if price is None:
        return None
    fees = _float(tx.get("fees")) or 0.0
    return price * qty + fees if acquisition else price * qty - fees


def _settled_cash(tx: Mapping[str, Any], qty: float, *, acquisition: bool) -> float | None:
    """Unsigned settled GBP value: ``amount_minor`` if non-zero, else price x units +/- fees.

    This is the magnitude of the trade's cash effect; the caller applies the
    direction from ``_SETTLED_TRADES``, so either sign convention works.

    ``amount_minor`` is the cash that actually settled, so it is already *net*
    of fees: the total paid on an acquisition (fees included) and the proceeds
    received on a disposal (fees deducted).  That is what Portfolio Performance
    exports as a portfolio transaction's ``amount`` (copied verbatim, with no
    ``fees`` field, by ``convert_portfolio_xml_to_account_transactions``), and
    it is the same figure credited to cash under ``trade_cash_effects``, so
    ``fees`` is never subtracted from it again.  Only the price x units
    fallback, a gross figure, applies ``fees`` -- so both paths yield the same
    net value.

    A zero ``amount_minor`` (common on transfers-in) records no value, so it is
    treated as unknown rather than as a known value of nothing.
    """
    amount_minor = _float(tx.get("amount_minor"))
    if amount_minor:
        return abs(amount_minor) / 100.0
    return _priced_value(tx, qty, acquisition=acquisition)


def _settled_cost(tx: Mapping[str, Any], qty: float, *, warn: bool) -> float | None:
    """Allowable cost of an acquisition: a positive ``amount_minor``, else price x units + fees.

    A negative ``amount_minor`` cannot be trusted as a cost (it may be a
    cash-outflow sign convention or a reversal), so rather than silently
    flipping its sign the cost falls back to the priced value, or to unknown.
    """
    amount_minor = _float(tx.get("amount_minor"))
    if amount_minor is not None and amount_minor < 0:
        if warn:
            logger.warning(
                "Ignoring negative amount_minor on %s of %s as an acquisition cost",
                sanitise_log_value(tx.get("type")),
                sanitise_log_value(tx.get("ticker") or tx.get("instrument_name")),
            )
        return _priced_value(tx, qty, acquisition=True)
    return _settled_cash(tx, qty, acquisition=True)


def _name(record: Mapping[str, Any]) -> str | None:
    for key in ("instrument_name", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def name_aliases(
    transactions: Sequence[Mapping[str, Any]], existing: Sequence[Mapping[str, Any]] = ()
) -> dict[str, str]:
    """Map instrument names to tickers so ticker-less trades join the right pool."""
    aliases: dict[str, str] = {}
    for record in [*existing, *transactions]:
        ticker = canonical_ticker(str(record.get("ticker") or ""))
        name = _name(record)
        if ticker and name:
            aliases.setdefault(name, ticker)
    return aliases


def _instrument_key(tx: Mapping[str, Any], aliases: Mapping[str, str]) -> str | None:
    # "BP." and "BP.L" are one LSE listing and must replay into one pool (#8600).
    ticker = canonical_ticker(str(tx.get("ticker") or ""))
    if ticker:
        return ticker
    name = _name(tx)
    if name is not None:
        return aliases.get(name, f"name:{name}")
    # Portfolio Performance rows whose security could not be resolved still
    # identify the same instrument by reference, so they can share a pool.
    ref = str(tx.get("security_ref") or "").strip()
    return f"ref:{ref}" if ref else None


def _sort_key(indexed: tuple[int, Mapping[str, Any]]) -> tuple[int, str, int, int]:
    """Dated rows by date (acquisitions first); undated rows last, in file order."""
    idx, tx = indexed
    tx_type = str(tx.get("type") or "").upper()
    day = str(tx.get("date") or "")[:10]
    if not _ISO_DATE_RE.match(day):
        return (1, "", 0, idx)
    return (0, day, 0 if tx_type in _ACQUIRE else 1, idx)


@dataclass(frozen=True)
class Disposal:
    """One disposal as replayed through its instrument's pool."""

    index: int
    tx_type: str
    units: float
    cost_gbp: float
    unknown_cost_units: float
    unmatched_units: float
    proceeds_gbp: float | None


@dataclass
class Replay:
    """Result of replaying a transactions list."""

    positions: dict[str, Position]
    cash: float = 0.0
    cash_seen: bool = False
    warn: bool = True
    on_disposal: Callable[[Disposal], None] | None = None


def _apply_trade(replay: Replay, index: int, tx: Mapping[str, Any], tx_type: str, key: str, trade_cash: bool) -> None:
    qty = _quantity(tx)
    if not qty:
        if replay.warn:
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
    value = _settled_cash(tx, qty, acquisition=acquisition)
    if acquisition:
        position.acquire(qty, _settled_cost(tx, qty, warn=replay.warn), str(tx.get("date") or "")[:10])
    else:
        cost_out, unknown_out, unmatched = position.dispose(qty)
        if replay.on_disposal is not None:
            replay.on_disposal(Disposal(index, tx_type, qty, cost_out, unknown_out, unmatched, value))
        if unmatched > _EPS and replay.warn:
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
    on_disposal: Callable[[Disposal], None] | None = None,
    warn: bool = True,
) -> Replay:
    """Replay ``transactions`` in date order (acquisitions first within a day, undated last).

    ``on_disposal`` is called for every disposal of a non-cash instrument with
    its index into ``transactions``.  ``warn=False`` silences data-quality
    warnings for callers that replay on every read.
    """
    replay = Replay(positions={}, warn=warn, on_disposal=on_disposal)
    aliases = aliases or {}
    cash_signs = {**_CASH_FLOWS, **(_CHARGES if trade_cash else {})}
    for idx, tx in sorted(enumerate(transactions), key=_sort_key):
        tx_type = str(tx.get("type") or "").upper()
        if tx_type in _ACQUIRE or tx_type in _DISPOSE:
            key = _instrument_key(tx, aliases)
            if key is None:
                if warn:
                    logger.warning("Skipping %s with neither ticker nor instrument_name", sanitise_log_value(tx_type))
                continue
            _apply_trade(replay, idx, tx, tx_type, key, trade_cash)
        elif tx_type in cash_signs:
            _apply_cash(replay, tx, cash_signs[tx_type])
    return replay


def transaction_cost_hints(transactions: Sequence[Mapping[str, Any]]) -> dict[str, tuple[float | None, str | None]]:
    """Map ticker -> ``(pool_cost, unknown_cost_since)`` for positions still held.

    ``pool_cost`` is the Section 104 cost when every held unit has a known
    cost, else ``None``.  ``unknown_cost_since`` is the date the units of
    unknown cost (typically an opening ``TRANSFER_IN``) first arrived.
    Read-time callers use these for holdings whose stored cost is 0, instead of
    reporting a false break-even.
    """
    replay = replay_transactions(transactions, aliases=name_aliases(transactions), warn=False)
    hints: dict[str, tuple[float | None, str | None]] = {}
    for key, pos in replay.positions.items():
        if pos.units <= _EPS:
            continue
        hints[key] = (round(pos.cost, 2) if pos.cost_known else None, pos.unknown_cost_since)
    return hints


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
    elif old_value is not None and not old_units and units:
        # A zero-unit placeholder has no last known price, and its value_gbp
        # describes no real position (#8110): value the new units at cost.
        holding["value_gbp"] = cost
    return holding


def _computed_holdings(replay: Replay, previous: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, position in replay.positions.items():
        if position.units <= _EPS:
            continue
        if key.startswith(("name:", "ref:")):
            logger.warning("No ticker known for %s; position left out of holdings", sanitise_log_value(key))
            continue
        prev = previous.get(key)
        units = round(position.units, 8)
        out[key] = _merge_holding(key, units, _cost_basis(position, prev), position.acquired_date, prev)
    cash = round(replay.cash, 2)
    if replay.cash_seen and abs(cash) >= 0.005:
        out[CASH_TICKER] = _merge_holding(CASH_TICKER, cash, cash, None, previous.get(CASH_TICKER))
    return out


def _tracked_instruments(transactions: Sequence[Mapping[str, Any]], aliases: Mapping[str, str]) -> set[str]:
    """Instrument keys any trade or transfer mentions, including ones since sold down to zero.

    Derived from the transactions themselves rather than the replay's
    positions, so it holds whether or not the replay keeps empty positions.
    """
    keys = set()
    for tx in transactions:
        if str(tx.get("type") or "").upper() in _ACQUIRE | _DISPOSE:
            key = _instrument_key(tx, aliases)
            if key is not None:
                keys.add(key)
    return keys


def _holdings_by_ticker(old_holdings: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Key existing holdings by canonical ticker, keeping one entry per instrument.

    ``BP.`` and ``BP.L`` are one instrument (#8600). When a document holds both,
    keep the entry already stored under the canonical key (``BP.L``), whatever
    the list order; if neither or both are, keep the later one. Log it, since
    the other entry's carried-forward fields are dropped.
    """
    previous: dict[str, Mapping[str, Any]] = {}
    for h in old_holdings:
        if not h.get("ticker"):
            continue
        key = canonical_ticker(str(h.get("ticker")))
        kept = previous.get(key)
        if kept is not None:
            kept_is_canonical = str(kept.get("ticker")).strip().upper() == key
            new_is_canonical = str(h.get("ticker")).strip().upper() == key
            winner = kept if kept_is_canonical and not new_is_canonical else h
            logger.warning(
                "holdings %s and %s are both %s; keeping %s",
                sanitise_log_value(kept.get("ticker")),
                sanitise_log_value(h.get("ticker")),
                sanitise_log_value(key),
                sanitise_log_value(winner.get("ticker")),
            )
            h = winner
        previous[key] = h
    return previous


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
    previous = _holdings_by_ticker(old_holdings)

    aliases = name_aliases(transactions, old_holdings)
    replay = replay_transactions(transactions, trade_cash=tx_data.get(TRADE_CASH_FLAG) is True, aliases=aliases)
    computed = _computed_holdings(replay, previous)
    tracked = _tracked_instruments(transactions, aliases)
    if replay.cash_seen:
        tracked.add(CASH_TICKER)
    # Keep the existing ordering so the rewritten file diffs cleanly. A
    # holding no transaction mentions (entered by hand before /input recorded
    # opening-balance transactions, or imported as a holdings snapshot) is not
    # the transactions' to remove, so it is carried forward as-is.
    ordered = [
        computed.pop(t) if t in computed else dict(h) for t, h in previous.items() if t in computed or t not in tracked
    ]
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
