from typing import Optional

import pandas as pd
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from backend.utils.html_render import render_timeseries_html


def apply_scaling(df: pd.DataFrame, scale: float) -> pd.DataFrame:
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns and df[col].notna().any():
            df[col] = df[col] * scale
    return df

import json

def get_scaling_override(ticker: str, exchange: str, requested_scaling: Optional[float]) -> float:
    if requested_scaling is not None:
        return requested_scaling

    try:
        with open("backend/timeseries/scaling_overrides.json") as f:
            overrides = json.load(f)
        return overrides.get(exchange, {}).get(ticker, 1.0)
    except Exception:
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
