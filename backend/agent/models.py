from __future__ import annotations

"""Pydantic models used by the trading agent."""

from pydantic import BaseModel, ConfigDict
from typing import Literal, Optional


class TradingSignal(BaseModel):
    """Represents a simple trading signal.

    Attributes:
        ticker: The instrument symbol.
        action: Recommended action, either ``"BUY"`` or ``"SELL"``.
        reason: Human readable description of why the signal was generated.
        confidence: Optional confidence score between 0 and 1.
        rationale: Optional detailed explanation of the signal.
    """

    ticker: str
    action: Literal["BUY", "SELL"]
    reason: str
    confidence: Optional[float] = None
    rationale: Optional[str] = None

    model_config = ConfigDict(extra="ignore")
