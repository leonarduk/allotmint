import datetime
import json
import re
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from backend.common.currency import extract_currency
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

    path = Path(__file__).resolve().parents[2] / "data" / "scaling_overrides.json"
    configured_data_root = getattr(config, "data_root", None)
    if configured_data_root:
        candidate = Path(str(configured_data_root)).expanduser()
        candidate_path = candidate / "scaling_overrides.json"
        if candidate_path.exists():
            path = candidate_path
    configured_repo_root = getattr(config, "repo_root", None)
    if configured_repo_root:
        candidate = Path(str(configured_repo_root)).expanduser() / "data" / "scaling_overrides.json"
        if candidate.exists():
            path = candidate
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

    full = base if not ex else f"{base}.{ex}"
    currency = None

    try:  # Prefer instrument metadata when available
        from backend.common.instruments import get_instrument_meta  # type: ignore

        try:
            inst_meta = get_instrument_meta(full) or {}
            if not inst_meta and full != base:
                inst_meta = get_instrument_meta(base) or {}
        except Exception:
            inst_meta = {}
        currency = extract_currency(inst_meta)
    except Exception:
        currency = None

    if not currency:
        try:
            from backend.common import portfolio_utils  # type: ignore

            try:
                sec_meta = portfolio_utils.get_security_meta(full) or portfolio_utils.get_security_meta(base)
            except Exception:
                sec_meta = None
            currency = extract_currency(sec_meta)
        except Exception:
            currency = None

    if currency is not None:
        return currency.pence_factor
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


def resolve_date_range(
    days: int,
    *,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> Tuple[datetime.date, datetime.date]:
    """Resolve a ``(start_date, end_date)`` window for timeseries queries.

    If *start_date* and/or *end_date* are supplied explicitly they take
    precedence over the computed value for that bound.  When only *days* is
    given the defaults are:

    - ``end_date``   → yesterday (``today - 1 day``)
    - ``start_date`` → ``today - days``; ``date(1900, 1, 1)`` when
      ``days <= 0`` (meaning "all available history").

    Parameters
    ----------
    days:
        Lookback window in calendar days.  Only used when the corresponding
        explicit date is ``None``.
    start_date:
        Optional explicit start bound.  Overrides the ``days`` calculation.
    end_date:
        Optional explicit end bound.  Overrides the default yesterday anchor.

    Returns
    -------
    tuple[date, date]
        A ``(start_date, end_date)`` pair ready to pass to
        ``load_meta_timeseries_range`` or any other range-aware loader.
    """
    if end_date is None:
        end_date = datetime.date.today() - datetime.timedelta(days=1)
    if start_date is None:
        if days <= 0:
            start_date = datetime.date(1900, 1, 1)
        else:
            start_date = datetime.date.today() - datetime.timedelta(days=days)
    return start_date, end_date
