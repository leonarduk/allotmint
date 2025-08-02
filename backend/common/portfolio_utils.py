import pathlib
import json
from collections import defaultdict
from typing import Set, Dict, Any, List

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_LOCAL_PLOTS_ROOT = _REPO_ROOT / "data-sample" / "plots"

import pathlib
import json
from typing import Set

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_LOCAL_PLOTS_ROOT = _REPO_ROOT / "data-sample" / "plots"


from pathlib import Path
import json
from typing import Set

def list_all_unique_tickers() -> list[str]:
    from pathlib import Path
    import json
    from typing import Set

    base = Path(__file__).resolve().parents[2] / "data-sample" / "plots"
    print(f"[DEBUG] Searching for account files under: {base}")

    tickers: Set[str] = set()
    matched = list(base.glob("*/*.json"))  # ← changed this line
    print(f"[DEBUG] Found {len(matched)} account files")

    for f in matched:
        if f.name == "person.json":
            continue  # skip metadata

        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for h in data.get("holdings", []):
                if tkr := h.get("ticker"):
                    tickers.add(tkr.upper())
        except Exception as e:
            print(f"[WARN] Failed to read {f}: {e}")

    print(f"[DEBUG] Found {len(tickers)} unique tickers")
    return sorted(tickers)

def aggregate_by_ticker(group_portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Collapse *group portfolio* down to one row per ticker, enriched with:
        • last_price_gbp, last_price_date
        • change_7d_pct, change_30d_pct
    """
    import datetime as dt
    from backend.common.prices import (
        get_latest_closing_prices,
        load_prices_for_tickers,
    )
    from backend.timeseries.fetch_meta_timeseries import run_all_tickers

    def _price_at(df, ticker: str, target: dt.date) -> float | None:
        if df.empty or "ticker" not in df.columns:
            return None
        sub = df[(df["ticker"] == ticker) & (df["date"] <= target.isoformat())]
        return float(sub.iloc[-1]["close_gbp"]) if not sub.empty else None

    agg: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: dict(
            ticker="",
            name="",
            units=0.0,
            market_value_gbp=0.0,
            gain_gbp=0.0,
        )
    )

    for acct in group_portfolio.get("accounts", []):
        for h in acct.get("holdings", []):
            row = agg[h["ticker"]]
            row["ticker"] = h["ticker"]
            row["name"] = h.get("name", h["ticker"])
            row["units"] += h.get("units", 0.0)
            row["market_value_gbp"] += h.get("market_value_gbp", 0.0)
            row["gain_gbp"] += h.get("unrealized_gain_gbp", 0.0)

    if not agg:
        return []

    tickers = sorted(agg.keys())
    run_all_tickers(tickers)

    latest = get_latest_closing_prices()
    today = dt.date.today()
    d7, d30 = today - dt.timedelta(days=7), today - dt.timedelta(days=30)
    ts_df = load_prices_for_tickers(tickers)

    for tkr, row in agg.items():
        last_p = latest.get(tkr)
        row["last_price_gbp"] = last_p
        row["last_price_date"] = today.isoformat()

        p7 = _price_at(ts_df, tkr, d7)
        p30 = _price_at(ts_df, tkr, d30)

        row["change_7d_pct"] = None if p7 in (None, 0) or last_p is None else (last_p - p7) / p7 * 100
        row["change_30d_pct"] = None if p30 in (None, 0) or last_p is None else (last_p - p30) / p30 * 100

    return sorted(agg.values(), key=lambda r: r["market_value_gbp"], reverse=True)
