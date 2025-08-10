from __future__ import annotations

import datetime as dt
from typing import List

from pydantic import BaseModel, Field, model_validator


class VirtualHolding(BaseModel):
    ticker: str
    units: float
    purchase_price: float
    purchase_date: dt.date
    watchlist: bool = False


class VirtualPortfolio(BaseModel):
    name: str
    description: str | None = None
    owner: str | None = None
    account: str | None = None
    holdings: List[VirtualHolding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_real_holdings(self) -> "VirtualPortfolio":
        """Ensure referenced holdings exist when owner/account provided."""
        if self.owner and self.account:
            try:
                from backend.common.data_loader import load_account

                acct = load_account(self.owner, self.account)
                real = {h.get("ticker") for h in acct.get("holdings", [])}
            except Exception as exc:  # pragma: no cover - load failure is fatal
                raise ValueError(
                    f"Unknown owner/account: {self.owner}/{self.account}"
                ) from exc

            for h in self.holdings:
                if h.watchlist or h.units == 0:
                    continue  # allow watchlist entries / zero-unit placeholders
                if h.ticker not in real:
                    raise ValueError(
                        f"Holding {h.ticker} not found in {self.owner}/{self.account}"
                    )
        return self
