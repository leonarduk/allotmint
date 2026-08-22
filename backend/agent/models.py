from __future__ import annotations

"""Pydantic models used by the trading agent."""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TradingSignal(BaseModel):
    """Represents a simple trading signal.

    Attributes:
        ticker: The instrument symbol.
        action: Recommended action, either ``"BUY"`` or ``"SELL"``.
        reason: Human readable description of why the signal was generated.
        confidence: Optional confidence score between 0 and 1.
        rationale: Optional detailed explanation of the signal.
        factors: Optional list of plain-English statements describing the
            indicators that support the recommendation.
        checks_skipped: Names of compliance/screening checks that were
            skipped because ``allotmint-pro`` is not installed, e.g.
            ``["compliance", "fundamental_screen"]``. Empty when every
            applicable check ran.
    """

    ticker: str
    action: Literal["BUY", "SELL"]
    reason: str
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    factors: Optional[List[str]] = None
    checks_skipped: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")
