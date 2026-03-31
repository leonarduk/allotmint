from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import pandas as pd

_PENCE_CODES = {"GBX", "GBXP", "GBPX"}


@dataclass(frozen=True)
class CurrencyNormaliser:
    """Single source of truth for currency normalisation and GBP conversion."""

    raw: Optional[str]
    canonical: str
    display_code: str
    is_pence: bool

    @classmethod
    def from_raw(cls, raw_currency: object) -> "CurrencyNormaliser":
        if raw_currency is None:
            return cls(raw=None, canonical="GBP", display_code="GBP", is_pence=False)

        text = str(raw_currency).strip()
        if not text:
            return cls(raw=None, canonical="GBP", display_code="GBP", is_pence=False)

        upper = text.upper()
        is_gbpence = len(text) == 3 and text[:2].upper() == "GB" and text[2] == "p"
        is_pence = upper in _PENCE_CODES or is_gbpence

        canonical = "GBX" if is_pence else upper
        display_code = "GBP" if is_pence else canonical
        return cls(raw=text, canonical=canonical, display_code=display_code, is_pence=is_pence)

    @property
    def pence_factor(self) -> float:
        return 0.01 if self.is_pence else 1.0

    def scale_dataframe(self, df: pd.DataFrame, scale_volume: bool = False) -> pd.DataFrame:
        """Apply pence scaling to known OHLC columns when needed."""
        if self.pence_factor == 1.0:
            return df

        out = df.copy()
        name_map = {c.lower(): c for c in out.columns}

        for logical in ("open", "high", "low", "close"):
            if logical in name_map:
                col = name_map[logical]
                out[col] = pd.to_numeric(out[col], errors="coerce") * self.pence_factor

        if scale_volume and "volume" in name_map:
            col = name_map["volume"]
            out[col] = pd.to_numeric(out[col], errors="coerce") * self.pence_factor

        return out

    def to_gbp(
        self,
        value: float,
        fx_cache: Optional[Dict[str, float]] = None,
        fx_rate_resolver: Optional[Callable[[str, str, Dict[str, float]], float]] = None,
    ) -> float:
        """Convert a scalar ``value`` in ``canonical`` currency to GBP."""
        if self.is_pence:
            return value * self.pence_factor

        if self.canonical == "GBP":
            return value

        if fx_rate_resolver is None:
            from backend.common.portfolio_utils import _fx_to_base

            fx_rate_resolver = _fx_to_base

        cache = fx_cache if fx_cache is not None else {}
        fx_rate = fx_rate_resolver(self.canonical, "GBP", cache)

        try:
            rate = float(fx_rate)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid FX rate for {self.canonical}->GBP: {fx_rate!r}") from exc

        if not pd.notna(rate) or rate <= 0:
            raise ValueError(f"Invalid FX rate for {self.canonical}->GBP: {fx_rate!r}")

        return value * rate


def extract_currency(meta: Optional[dict[str, Any]]) -> Optional[CurrencyNormaliser]:
    """Extract normalised currency from metadata payloads."""
    if not isinstance(meta, dict):
        return None

    for key in (
        "currency",
        "Currency",
        "price_currency",
        "priceCurrency",
        "quote_currency",
        "quoteCurrency",
        "currencyCode",
    ):
        if key in meta and meta[key] is not None:
            return CurrencyNormaliser.from_raw(meta[key])

    for nested in ("price", "quote"):
        block = meta.get(nested)
        if isinstance(block, dict):
            value = block.get("currency") or block.get("Currency")
            if value is not None:
                return CurrencyNormaliser.from_raw(value)

    return None
