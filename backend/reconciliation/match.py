"""Deterministic matching of extracted statement rows against the ledger (#10474).

Pure: no I/O and no LLM. Statement rows are paired with ledger transactions
by type, instrument and date (within ``date_tolerance_days``), comparing
amounts in pence. Exact pairs are taken first so a near miss can never steal
a row that matches perfectly elsewhere; the rest are paired as mismatches.
Whatever is left on either side, plus any closing cash or unit difference, is
reported as a :class:`Diff` with a suggested ledger change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, get_args

from backend.common import holdings_rebuild
from backend.common.ticker_utils import canonical_ticker
from backend.common.transaction_reconciliation import _transactions_to_positions
from backend.reconciliation.models import (
    TRADE_TYPES,
    Diff,
    Match,
    StatementExtraction,
    StatementRow,
    StatementRowType,
    SuggestedChange,
    SuggestedRequest,
    minor_to_pounds,
    pounds_to_minor,
)

DEFAULT_DATE_TOLERANCE_DAYS = 3
RECONCILIATION_REASON = "Statement reconciliation"
_UNITS_TOLERANCE = 1e-4
_MIN_AMOUNT_TOLERANCE_MINOR = 2
_RELATIVE_AMOUNT_TOLERANCE = 0.001

# Ledger spellings folded onto the statement's type vocabulary.
_TYPE_ALIASES = {"PURCHASE": "BUY", "DIVIDENDS": "DIVIDEND"}
_STATEMENT_TYPES = frozenset(get_args(StatementRowType))


def _gbp(minor: int) -> str:
    sign = "-" if minor < 0 else ""
    return f"{sign}£{minor_to_pounds(abs(minor)):,.2f}"


def _amounts_close(a: Optional[int], b: Optional[int]) -> bool:
    if a is None or b is None:
        return True
    return abs(a - b) <= max(_MIN_AMOUNT_TOLERANCE_MINOR, int(max(abs(a), abs(b)) * _RELATIVE_AMOUNT_TOLERANCE))


def _units_close(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= _UNITS_TOLERANCE


def _parse_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class LedgerRow:
    """A ledger transaction reduced to what matching compares, amounts in pence."""

    id: str
    date: Optional[date]
    type: str
    ticker: Optional[str]
    units: Optional[float]
    gross_minor: Optional[int]
    fees_minor: Optional[int]
    settled_minor: Optional[int]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_tx(cls, tx: Mapping[str, Any]) -> "LedgerRow":
        tx_type = str(tx.get("type") or tx.get("kind") or "").upper()
        units = _float(tx.get("units"))
        if units is None:
            units = holdings_rebuild.transaction_quantity(tx)
        price = _float(tx.get("price_gbp"))
        amount = _float(tx.get("amount_minor"))
        return cls(
            id=str(tx.get("id") or ""),
            date=_parse_date(tx.get("date")),
            type=_TYPE_ALIASES.get(tx_type, tx_type),
            ticker=canonical_ticker(tx.get("ticker")) or None,
            units=units,
            gross_minor=pounds_to_minor(price * units) if price is not None and units is not None else None,
            fees_minor=pounds_to_minor(_float(tx.get("fees"))),
            settled_minor=int(round(abs(amount))) if amount else None,
            raw=tx,
        )


def _statement_ticker(
    row_ticker: Optional[str], isin: Optional[str], isin_to_ticker: Mapping[str, str]
) -> Optional[str]:
    if row_ticker:
        return row_ticker
    return isin_to_ticker.get(isin) if isin else None


def _instrument_ok(statement_ticker: Optional[str], ledger: LedgerRow) -> bool:
    # A statement row with no resolvable instrument is matched on type,
    # date and amount alone; a cash row in the ledger often has no ticker.
    return statement_ticker is None or ledger.ticker is None or statement_ticker == ledger.ticker


def _ledger_settled(ledger: LedgerRow, row_type: str) -> Optional[int]:
    if ledger.settled_minor is not None:
        return ledger.settled_minor
    if ledger.gross_minor is None:
        return None
    fees = ledger.fees_minor or 0
    return ledger.gross_minor + fees if row_type == "BUY" else ledger.gross_minor - fees


@dataclass
class _Comparison:
    """How one statement row compares with one candidate ledger row."""

    units_ok: bool
    amount_ok: bool
    fee_ok: bool
    statement_minor: Optional[int]
    ledger_minor: Optional[int]

    @property
    def exact(self) -> bool:
        return self.units_ok and self.amount_ok and self.fee_ok


def _compare(row: StatementRow, ledger: LedgerRow) -> _Comparison:
    if row.type not in TRADE_TYPES:
        return _Comparison(
            True, _amounts_close(row.amount_minor, ledger.settled_minor), True, row.amount_minor, ledger.settled_minor
        )
    units_ok = _units_close(row.units, ledger.units)
    if ledger.gross_minor is not None and row.consideration_minor is not None:
        # Gross vs gross; fees are compared on their own so a wrong fee is
        # reported as a fee mismatch, not a price problem.
        amount_ok = _amounts_close(row.consideration_minor, ledger.gross_minor)
        fee_ok = row.fees_minor == (ledger.fees_minor or 0)
        return _Comparison(units_ok, amount_ok, fee_ok, row.consideration_minor, ledger.gross_minor)
    statement_settled = row.amount_minor
    if statement_settled is None and row.consideration_minor is not None:
        statement_settled = row.consideration_minor + (row.fees_minor if row.type == "BUY" else -row.fees_minor)
    ledger_settled = _ledger_settled(ledger, row.type)
    return _Comparison(
        units_ok, _amounts_close(statement_settled, ledger_settled), True, statement_settled, ledger_settled
    )


@dataclass
class _Context:
    owner: str
    account: str
    isin_to_ticker: Mapping[str, str]
    tolerance: timedelta


def _candidates(row: StatementRow, ledger: Sequence[LedgerRow], used: set[str], ctx: _Context) -> List[LedgerRow]:
    ticker = _statement_ticker(row.ticker, row.isin, ctx.isin_to_ticker)
    return [
        tx
        for tx in ledger
        if tx.id not in used
        and tx.type == row.type
        and tx.date is not None
        and abs(tx.date - row.date) <= ctx.tolerance
        and _instrument_ok(ticker, tx)
    ]


def _best(
    row: StatementRow, candidates: Iterable[LedgerRow], accept: Callable[[_Comparison], bool]
) -> Optional[Tuple[LedgerRow, _Comparison]]:
    scored = []
    for position, tx in enumerate(candidates):
        comparison = _compare(row, tx)
        if not accept(comparison):
            continue
        gap = abs((comparison.statement_minor or 0) - (comparison.ledger_minor or 0))
        scored.append(((abs((tx.date - row.date).days), gap, position), tx, comparison))  # type: ignore[operator]
    if not scored:
        return None
    _, tx, comparison = min(scored, key=lambda item: item[0])
    return tx, comparison


def _near_miss(row: StatementRow, comparison: _Comparison) -> bool:
    # A trade must at least agree on units to be "the same trade, wrong
    # amount"; a cash row only has its type and date to go on.
    return comparison.units_ok if row.type in TRADE_TYPES else True


def _create_request(row: StatementRow, ticker: Optional[str], ctx: _Context) -> Optional[SuggestedRequest]:
    body: Dict[str, Any] = {
        "owner": ctx.owner,
        "account": ctx.account,
        "date": row.date.isoformat(),
        "type": row.type,
        "reason": RECONCILIATION_REASON,
        "comments": f"From broker statement: {row.description}" if row.description else "From broker statement",
    }
    if row.type in TRADE_TYPES:
        if not ticker or not row.units or not row.consideration_minor:
            return None
        body.update(
            ticker=ticker,
            units=row.units,
            price_gbp=round(minor_to_pounds(row.consideration_minor) / row.units, 6),
            fees=minor_to_pounds(row.fees_minor),
        )
    else:
        if not row.amount_minor:
            return None
        body["amount_minor"] = row.amount_minor
        if ticker:
            body["ticker"] = ticker
    return SuggestedRequest(method="POST", path="/transactions", body=body)


def _missing_from_ledger(row: StatementRow, ctx: _Context) -> Diff:
    ticker = _statement_ticker(row.ticker, row.isin, ctx.isin_to_ticker)
    amount = row.consideration_minor if row.type in TRADE_TYPES else row.amount_minor
    what = f"{row.type} {ticker or row.isin or row.description or ''}".strip()
    request = _create_request(row, ticker, ctx)
    if request is None:
        description = (
            f"Add this {row.type} row by hand: the statement does not identify the instrument or amount clearly enough"
        )
    else:
        description = f"Add this {row.type} row" + (f" ({_gbp(amount)})" if amount else "")
    return Diff(
        kind="missing_from_ledger",
        message=f"{what} on {row.date} is on the statement but not in the ledger",
        statement_index=row.index,
        ticker=ticker,
        date=row.date,
        statement_minor=amount,
        statement_units=row.units,
        suggestion=SuggestedChange(description=description, request=request),
    )


def _fee_update_request(row: StatementRow, ledger: LedgerRow, ctx: _Context) -> Optional[SuggestedRequest]:
    raw = ledger.raw
    if ledger.type not in TRADE_TYPES or ledger.date is None or raw.get("price_gbp") is None or not ledger.units:
        return None
    body = {
        "owner": ctx.owner,
        "account": ctx.account,
        "ticker": raw.get("ticker"),
        "date": ledger.date.isoformat(),
        "type": ledger.type,
        "price_gbp": raw.get("price_gbp"),
        "units": ledger.units,
        "fees": minor_to_pounds(row.fees_minor),
        "reason": raw.get("reason") or RECONCILIATION_REASON,
        "comments": raw.get("comments"),
    }
    return SuggestedRequest(method="PUT", path=f"/transactions/{ledger.id}", body=body)


def _mismatch_diffs(row: StatementRow, ledger: LedgerRow, comparison: _Comparison, ctx: _Context) -> List[Diff]:
    diffs: List[Diff] = []
    base: Dict[str, Any] = dict(
        statement_index=row.index, ledger_id=ledger.id, ticker=ledger.ticker or row.ticker, date=row.date
    )
    if not comparison.fee_ok:
        ledger_fees = ledger.fees_minor or 0
        diffs.append(
            Diff(
                kind="fee_mismatch",
                message=(
                    f"{row.type} {base['ticker'] or ''} on {row.date}: "
                    f"fee recorded as {_gbp(ledger_fees)}, statement says {_gbp(row.fees_minor)}"
                ),
                statement_minor=row.fees_minor,
                ledger_minor=ledger_fees,
                difference_minor=row.fees_minor - ledger_fees,
                suggestion=SuggestedChange(
                    description=f"Change the fee from {_gbp(ledger_fees)} to {_gbp(row.fees_minor)}",
                    request=_fee_update_request(row, ledger, ctx),
                ),
                **base,
            )
        )
    if not comparison.amount_ok:
        statement_minor, ledger_minor = comparison.statement_minor or 0, comparison.ledger_minor or 0
        diffs.append(
            Diff(
                kind="amount_mismatch",
                message=(
                    f"{row.type} {base['ticker'] or ''} on {row.date}: "
                    f"ledger has {_gbp(ledger_minor)}, statement says {_gbp(statement_minor)}"
                ),
                statement_minor=statement_minor,
                ledger_minor=ledger_minor,
                difference_minor=statement_minor - ledger_minor,
                statement_units=row.units,
                ledger_units=ledger.units,
                suggestion=SuggestedChange(
                    description="Check the price, units and amount of this ledger row against the statement and edit it"
                ),
                **base,
            )
        )
    return diffs


def _period(extraction: StatementExtraction) -> Tuple[Optional[date], Optional[date]]:
    dates = [row.date for row in extraction.rows]
    start = extraction.period_start or (min(dates) if dates else None)
    end = extraction.period_end or (max(dates) if dates else None)
    return start, end


def _missing_from_statement(ledger: LedgerRow) -> Diff:
    amount = (
        ledger.gross_minor if ledger.type in TRADE_TYPES and ledger.gross_minor is not None else ledger.settled_minor
    )
    return Diff(
        kind="missing_from_statement",
        message=f"{ledger.type} {ledger.ticker or ''} on {ledger.date} is in the ledger but not on the statement",
        ledger_id=ledger.id,
        ticker=ledger.ticker,
        date=ledger.date,
        ledger_minor=amount,
        ledger_units=ledger.units,
        suggestion=SuggestedChange(
            description=(
                "Check whether this ledger row is a duplicate, belongs to another account or period, "
                "or was cancelled; edit or delete it by hand if so"
            )
        ),
    )


def _pair_rows(
    extraction: StatementExtraction, ledger: Sequence[LedgerRow], ctx: _Context
) -> Tuple[List[Match], List[Diff], set[str]]:
    rows = sorted(extraction.rows, key=lambda r: (r.date, r.index))
    used: set[str] = set()
    paired: Dict[int, Tuple[LedgerRow, _Comparison]] = {}
    for exact_only in (True, False):
        for row in rows:
            if row.index in paired:
                continue
            accept = (lambda c: c.exact) if exact_only else (lambda c, row=row: _near_miss(row, c))
            best = _best(row, _candidates(row, ledger, used, ctx), accept)
            if best is not None:
                paired[row.index] = best
                used.add(best[0].id)
    matched: List[Match] = []
    diffs: List[Diff] = []
    for row in rows:
        if row.index not in paired:
            diffs.append(_missing_from_ledger(row, ctx))
            continue
        tx, comparison = paired[row.index]
        if comparison.exact:
            matched.append(Match(statement_index=row.index, ledger_id=tx.id))
        else:
            diffs.extend(_mismatch_diffs(row, tx, comparison, ctx))
    return matched, diffs, used


def _ledger_cash_minor(transactions: Sequence[Mapping[str, Any]], trade_cash: bool) -> Optional[int]:
    replay = holdings_rebuild.replay_transactions(transactions, trade_cash=trade_cash, warn=False)
    return pounds_to_minor(replay.cash) if replay.cash_seen else None


def _cash_diff(
    extraction: StatementExtraction, as_of: List[Mapping[str, Any]], trade_cash: bool, warnings: List[str]
) -> List[Diff]:
    closing = extraction.closing_cash_minor
    if closing is None:
        return []
    ledger_cash = _ledger_cash_minor(as_of, trade_cash)
    if ledger_cash is None:
        warnings.append("The ledger has no cash movements, so the statement's closing cash could not be compared")
        return []
    if abs(closing - ledger_cash) <= _MIN_AMOUNT_TOLERANCE_MINOR:
        return []
    difference = closing - ledger_cash
    return [
        Diff(
            kind="cash_mismatch",
            message=(
                f"Closing cash on the statement is {_gbp(closing)}; "
                f"the ledger implies {_gbp(ledger_cash)} (difference {_gbp(difference)})"
            ),
            date=extraction.period_end,
            statement_minor=closing,
            ledger_minor=ledger_cash,
            difference_minor=difference,
            suggestion=SuggestedChange(
                description="Accept the missing rows above first; any difference left is an unrecorded cash movement"
            ),
        )
    ]


def _units_diffs(
    extraction: StatementExtraction,
    as_of: List[Mapping[str, Any]],
    isin_to_ticker: Mapping[str, str],
    warnings: List[str],
) -> List[Diff]:
    if not extraction.closing_holdings:
        return []
    ledger_units: Dict[str, float] = {}
    for ticker, units in _transactions_to_positions(as_of).items():
        key = canonical_ticker(ticker)
        ledger_units[key] = ledger_units.get(key, 0.0) + units
    statement_units: Dict[str, float] = {}
    for holding in extraction.closing_holdings:
        resolved = _statement_ticker(holding.ticker, holding.isin, isin_to_ticker)
        if not resolved:
            warnings.append(f"Closing holding {holding.name or holding.isin or '?'} could not be matched to a ticker")
            continue
        statement_units[resolved] = statement_units.get(resolved, 0.0) + holding.units
    diffs = []
    for key in sorted(set(statement_units) | {k for k, v in ledger_units.items() if abs(v) > _UNITS_TOLERANCE}):
        if key == holdings_rebuild.CASH_TICKER:
            continue
        stated, held = statement_units.get(key, 0.0), ledger_units.get(key, 0.0)
        if _units_close(stated, held):
            continue
        diffs.append(
            Diff(
                kind="units_mismatch",
                message=f"{key}: statement shows {stated:g} units at the period end, the ledger implies {held:g}",
                ticker=key,
                date=extraction.period_end,
                statement_units=stated,
                ledger_units=held,
                suggestion=SuggestedChange(
                    description=(
                        "Accept the missing trades above first; any units left over need a BUY, SELL or transfer row"
                    )
                ),
            )
        )
    return diffs


def reconcile(
    extraction: StatementExtraction,
    ledger_transactions: Sequence[Mapping[str, Any]],
    *,
    owner: str,
    account: str,
    isin_to_ticker: Optional[Mapping[str, str]] = None,
    trade_cash: bool = False,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
) -> Tuple[List[Match], List[Diff], List[str]]:
    """Match ``extraction`` against one account's ledger; return ``(matched, diffs, warnings)``.

    ``ledger_transactions`` are dicts as ``GET /transactions`` returns them
    (each with its ``id``). ``trade_cash`` mirrors the account's
    ``trade_cash_effects`` flag so ledger cash is replayed as the holdings
    rebuild does.
    """
    ctx = _Context(owner, account, dict(isin_to_ticker or {}), timedelta(days=date_tolerance_days))
    warnings: List[str] = []
    ledger = [LedgerRow.from_tx(tx) for tx in ledger_transactions]
    matched, diffs, used = _pair_rows(extraction, ledger, ctx)

    start, end = _period(extraction)
    if extraction.document_type != "contract_note" and start and end:
        diffs.extend(
            _missing_from_statement(tx)
            for tx in ledger
            if tx.id not in used and tx.date is not None and start <= tx.date <= end and tx.type in _STATEMENT_TYPES
        )

    as_of = [tx for tx in ledger_transactions if end is None or (_parse_date(tx.get("date")) or date.min) <= end]
    diffs.extend(_cash_diff(extraction, as_of, trade_cash, warnings))
    diffs.extend(_units_diffs(extraction, as_of, ctx.isin_to_ticker, warnings))
    return matched, diffs, warnings
