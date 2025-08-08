import datetime
import re
from typing import Optional

import pandas as pd
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from backend.utils.html_render import render_timeseries_html

STANDARD_COLUMNS = [
    "Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"
]

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

import json

def get_scaling_override(ticker: str, exchange: str, requested_scaling: Optional[float]) -> float:
    if requested_scaling is not None:
        return requested_scaling

    try:
        with open("data/scaling_overrides.json") as f:
            ov = json.load(f)
    except Exception:
        return 1.0

    base = re.split(r"[.:]", ticker)[0].upper()
    ex = (exchange or "").upper()

    # Try: exact → base → per‑exchange wildcard → global wildcard
    candidates = [
        (ex, ticker), (ex, base),
        (ex, "*"), ("*", base), ("*", "*"),
    ]
    for ex_key, t_key in candidates:
        if ex_key in ov and t_key in ov[ex_key]:
            try:
                return float(ov[ex_key][t_key])
            except Exception:
                pass
    return 1.0

def handle_timeseries_response(
    df: pd.DataFrame,
    format: str,
    title: str,
    subtitle: str
):
    if df.empty:
        return HTMLResponse("<h1>No data found</h1>", status_code=404)

    if format == "json":
        return JSONResponse(content=df.to_dict(orient="records"))
    elif format == "csv":
        return PlainTextResponse(content=df.to_csv(index=False), media_type="text/csv")
    else:
        return render_timeseries_html(df, title, subtitle)

# ── new helper ──────────────────────────────────────────────
def _nearest_weekday(d: datetime.date, forward: bool) -> datetime.date:
    """
    Return *d* if it’s a weekday; otherwise move to nearest weekday.

    forward=True  → Friday→Mon (skip weekend forward)
    forward=False → Saturday/Sunday→Fri (skip weekend backward)
    """
    while d.weekday() >= 5:   # 5 = Saturday, 6 = Sunday
        d += datetime.timedelta(days=1 if forward else -1)
    return d

def _is_isin(ticker: str) -> bool:
    base = re.split(r"[.:]", ticker)[0].upper()
    return len(base) == 12 and base.isalnum()
