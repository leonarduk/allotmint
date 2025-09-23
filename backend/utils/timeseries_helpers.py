import datetime
import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from backend.config import config
from backend.utils.html_render import render_timeseries_html

STANDARD_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]


def apply_scaling(df: pd.DataFrame, scale: float, scale_volume: bool = False) -> pd.DataFrame:
    if scale is None or scale == 1:
        return df
    df = df.copy()

    # Map lowercase -> actual column name
    name_map = {c.lower(): c for c in df.columns}

    for logical in ["open", "high", "low", "close"]:
        if logical in name_map:
            col = name_map[logical]
            df[col] = pd.to_numeric(df[col], errors="coerce") * scale

    if scale_volume and "volume" in name_map:
        col = name_map["volume"]
        df[col] = pd.to_numeric(df[col], errors="coerce") * scale

    return df


def get_scaling_override(ticker: str, exchange: str, requested_scaling: Optional[float]) -> float:
    if requested_scaling is not None:
        return requested_scaling

    repo_root = (
        Path(config.repo_root)
        if config.repo_root and ":" not in str(config.repo_root)
        else Path(__file__).resolve().parents[2]
    )
    path = repo_root / "data" / "scaling_overrides.json"
    try:
        with path.open() as f:
            ov = json.load(f)
    except Exception:
        ov = {}

    base = re.split(r"[.:]", ticker)[0].upper()
    ex = (exchange or "").upper()

    # Try: exact -> base -> per-exchange wildcard -> global wildcard
    candidates = [
        (ex, ticker),
        (ex, base),
        (ex, "*"),
        ("*", base),
        ("*", "*"),
    ]
    for ex_key, t_key in candidates:
        if ex_key in ov and t_key in ov[ex_key]:
            try:
                return float(ov[ex_key][t_key])
            except Exception:
                continue

    def _normalize_currency(value: object) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        upper = text.upper()
        # Treat variations like "GBp" as GBX (pence)
        if upper == "GBP" and text.lower().endswith("p"):
            return "GBX"
        if upper in {"GBX", "GBXP", "GBPX"}:
            return "GBX"
        return upper

    def _extract_currency(meta: Optional[dict]) -> Optional[str]:
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
                norm = _normalize_currency(meta[key])
                if norm:
                    return norm
        for nested in ("price", "quote"):
            block = meta.get(nested)
            if isinstance(block, dict):
                norm = _normalize_currency(block.get("currency") or block.get("Currency"))
                if norm:
                    return norm
        return None

    full = base if not ex else f"{base}.{ex}"
    currency: Optional[str] = None

    try:  # Prefer instrument metadata when available
        from backend.common.instruments import get_instrument_meta  # type: ignore

        try:
            inst_meta = get_instrument_meta(full) or {}
            if not inst_meta and full != base:
                inst_meta = get_instrument_meta(base) or {}
        except Exception:
            inst_meta = {}
        currency = _extract_currency(inst_meta)
    except Exception:
        currency = None

    if not currency:
        try:
            from backend.common import portfolio_utils  # type: ignore

            try:
                sec_meta = portfolio_utils.get_security_meta(full) or portfolio_utils.get_security_meta(base)
            except Exception:
                sec_meta = None
            currency = _extract_currency(sec_meta)
        except Exception:
            currency = None

    if currency == "GBX":
        return 0.01
    if currency:
        return 1.0
    return 1.0


def handle_timeseries_response(
    df: pd.DataFrame,
    format: str,
    title: str,
    subtitle: str,
    metadata: Optional[dict] = None,
):
    if df.empty:
        return HTMLResponse("<h1>No data found</h1>", status_code=404)

    if format == "json":
        payload = df.to_dict(orient="records")
        if metadata is not None:
            return JSONResponse(content={**metadata, "prices": payload})
        return JSONResponse(content=payload)
    elif format == "csv":
        return PlainTextResponse(content=df.to_csv(index=False), media_type="text/csv")
    else:
        return render_timeseries_html(df, title, subtitle)


# ── new helper ──────────────────────────────────────────────
def _nearest_weekday(d: datetime.date, forward: bool) -> datetime.date:
    """
    Return *d* if it's a weekday; otherwise move to nearest weekday.

    forward=True  -> Friday->Mon (skip weekend forward)
    forward=False -> Saturday/Sunday->Fri (skip weekend backward)
    """
    while d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        d += datetime.timedelta(days=1 if forward else -1)
    return d


def _is_isin(ticker: str) -> bool:
    base = re.split(r"[.:]", ticker)[0].upper()
    return len(base) == 12 and base.isalnum()
