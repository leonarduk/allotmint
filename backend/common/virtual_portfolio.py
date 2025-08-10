from __future__ import annotations

"""Utility models and helpers for user-defined virtual portfolios."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# Directory for storing virtual portfolio JSON files
VIRTUAL_PORTFOLIO_DIR = Path(__file__).resolve().parents[2] / "data" / "virtual_portfolios"


class VirtualHolding(BaseModel):
    """A simplified holding entry used by virtual portfolios."""

    ticker: str
    units: float
    name: Optional[str] = None
    currency: Optional[str] = None
    exchange: Optional[str] = None
    cost_gbp: Optional[float] = None
    market_value_gbp: Optional[float] = None


class VirtualPortfolio(BaseModel):
    """Top-level representation of a virtual portfolio."""

    id: str = Field(..., description="Unique identifier for the virtual portfolio")
    name: str
    holdings: List[VirtualHolding] = Field(default_factory=list)

    def as_portfolio_dict(self) -> Dict:
        """Return in the standard portfolio tree format."""
        return {
            "id": self.id,
            "name": self.name,
            "accounts": [
                {
                    "account_type": "virtual",
                    "currency": "GBP",
                    "holdings": [h.dict() for h in self.holdings],
                }
            ],
        }


class VirtualPortfolioSummary(BaseModel):
    id: str
    name: str


def _vp_path(vp_id: str) -> Path:
    VIRTUAL_PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    return VIRTUAL_PORTFOLIO_DIR / f"{vp_id}.json"


def list_virtual_portfolio_metadata() -> List[VirtualPortfolioSummary]:
    metas: List[VirtualPortfolioSummary] = []
    if not VIRTUAL_PORTFOLIO_DIR.exists():
        return metas
    for f in sorted(VIRTUAL_PORTFOLIO_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            metas.append(VirtualPortfolioSummary(id=data.get("id", f.stem), name=data.get("name", f.stem)))
        except Exception:
            continue
    return metas


def load_virtual_portfolio(vp_id: str) -> Optional[VirtualPortfolio]:
    path = _vp_path(vp_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return VirtualPortfolio(**data)


def save_virtual_portfolio(vp: VirtualPortfolio) -> VirtualPortfolio:
    path = _vp_path(vp.id)
    path.write_text(vp.json(indent=2))
    return vp


def delete_virtual_portfolio(vp_id: str) -> None:
    path = _vp_path(vp_id)
    if path.exists():
        path.unlink()


def list_virtual_portfolios() -> List[VirtualPortfolio]:
    return [vp for vp in (load_virtual_portfolio(m.id) for m in list_virtual_portfolio_metadata()) if vp]
