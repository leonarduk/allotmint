from __future__ import annotations

"""Pydantic models used by the trading agent."""

from pydantic import BaseModel, ConfigDict
from typing import Literal


class TradingSignal(BaseModel):
    """Represents a simple trading signal.

    Attributes:
        ticker: The instrument symbol.
        action: Recommended action, either ``"BUY"`` or ``"SELL"``.
        reason: Human readable description of why the signal was generated.
    """

    ticker: str
    action: Literal["BUY", "SELL"]
    reason: str

    model_config = ConfigDict(extra="ignore")
