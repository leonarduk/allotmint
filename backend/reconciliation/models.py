"""Schemas for statement reconciliation (#10474).

Two layers:

* ``Raw*`` models are what the LLM is asked to return. Money is in pounds as
  printed on the statement, because that is what the model reads; prices
  carry an explicit unit (``GBP`` or ``GBX``) instead of being guessed.
* ``Statement*`` models are the validated, normalised form the matcher works
  on. Every amount is an integer number of pence (``*_minor``) and every
  price is in pounds, so nothing downstream has to remember which unit a
  number is in.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ``_Date``, not ``date``, in annotations: a field named ``date`` would
# otherwise shadow the type for the fields declared after it.
_Date = date

# Ledger transaction types a statement row may map to. Pension contributions
# and tax-relief top-ups are both DEPOSITs in the ledger; the description
# keeps which one it was.
StatementRowType = Literal["BUY", "SELL", "DIVIDEND", "INTEREST", "DEPOSIT", "WITHDRAWAL", "FEES"]
TRADE_TYPES = frozenset({"BUY", "SELL"})
PriceUnit = Literal["GBP", "GBX"]


def pounds_to_minor(value: Optional[float]) -> Optional[int]:
    """Convert a pounds amount to whole pence, rounding half up; ``None`` stays ``None``."""
    if value is None:
        return None
    return int(Decimal(str(value)).scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def minor_to_pounds(value: int) -> float:
    return value / 100


class RawStatementRow(BaseModel):
    """One transaction as the LLM read it off the statement."""

    model_config = ConfigDict(extra="ignore")

    date: _Date
    type: StatementRowType
    description: Optional[str] = None
    ticker: Optional[str] = None
    isin: Optional[str] = None
    units: Optional[float] = Field(default=None, ge=0)
    price: Optional[float] = Field(default=None, ge=0)
    price_unit: PriceUnit = "GBP"
    consideration: Optional[float] = Field(default=None, ge=0)
    fees: Optional[float] = Field(default=None, ge=0)
    stamp_duty: Optional[float] = Field(default=None, ge=0)
    amount: Optional[float] = Field(default=None, ge=0)


class RawClosingHolding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: Optional[str] = None
    isin: Optional[str] = None
    name: Optional[str] = None
    units: float = Field(ge=0)


class RawStatement(BaseModel):
    """The full JSON object the extraction prompt asks for."""

    model_config = ConfigDict(extra="ignore")

    document_type: Optional[str] = None
    period_start: Optional[_Date] = None
    period_end: Optional[_Date] = None
    opening_cash: Optional[float] = None
    closing_cash: Optional[float] = None
    rows: List[RawStatementRow] = Field(default_factory=list)
    closing_holdings: List[RawClosingHolding] = Field(default_factory=list)


class StatementRow(BaseModel):
    """A validated statement row with every amount in pence.

    For trades ``consideration_minor`` is gross (units x price) and
    ``amount_minor`` is the settled total (consideration plus fees and stamp
    duty on a BUY, minus fees on a SELL). For cash rows only ``amount_minor``
    is set, and it is always positive: the type gives the direction.
    """

    index: int
    date: _Date
    type: StatementRowType
    description: Optional[str] = None
    ticker: Optional[str] = None
    isin: Optional[str] = None
    units: Optional[float] = None
    price_gbp: Optional[float] = None
    consideration_minor: Optional[int] = None
    fees_minor: int = 0
    amount_minor: Optional[int] = None
    flags: List[str] = Field(default_factory=list)


class ClosingHolding(BaseModel):
    ticker: Optional[str] = None
    isin: Optional[str] = None
    name: Optional[str] = None
    units: float


class StatementExtraction(BaseModel):
    document_type: Optional[str] = None
    period_start: Optional[_Date] = None
    period_end: Optional[_Date] = None
    opening_cash_minor: Optional[int] = None
    closing_cash_minor: Optional[int] = None
    rows: List[StatementRow] = Field(default_factory=list)
    closing_holdings: List[ClosingHolding] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


DiffKind = Literal[
    "missing_from_ledger",
    "missing_from_statement",
    "amount_mismatch",
    "fee_mismatch",
    "cash_mismatch",
    "units_mismatch",
]


class SuggestedRequest(BaseModel):
    """An existing transactions endpoint call that would apply a suggestion.

    The reconciliation endpoint never sends it; the UI does, one row at a
    time, after the user accepts it.
    """

    method: Literal["POST", "PUT"]
    path: str
    body: Dict[str, Any]


class SuggestedChange(BaseModel):
    description: str
    request: Optional[SuggestedRequest] = None


class Diff(BaseModel):
    kind: DiffKind
    message: str
    statement_index: Optional[int] = None
    ledger_id: Optional[str] = None
    ticker: Optional[str] = None
    date: Optional[_Date] = None
    statement_minor: Optional[int] = None
    ledger_minor: Optional[int] = None
    difference_minor: Optional[int] = None
    statement_units: Optional[float] = None
    ledger_units: Optional[float] = None
    suggestion: SuggestedChange


class Match(BaseModel):
    statement_index: int
    ledger_id: str


class ReconciliationResult(BaseModel):
    extracted: StatementExtraction
    matched: List[Match]
    diffs: List[Diff]
    warnings: List[str]
    llm_provider: str
    sent_to_cloud: bool
    explanation: Optional[str] = None
