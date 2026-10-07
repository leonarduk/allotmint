from __future__ import annotations

"""Custom query routes for analytics and saved queries."""

import io
import json
import os
import re
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Iterator, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from backend.common.account_scaffold import load_transactions
from backend.common.holding_utils import _get_price_for_date_scaled
from backend.common.path_utils import safe_join
from backend.common.portfolio_loader import get_units_as_of, list_portfolios
from backend.common.portfolio_utils import compute_var_with_basis, get_security_meta
from backend.config import config, demo_identity
from backend.timeseries.cache import load_meta_timeseries_range

router = APIRouter(prefix="/custom-query", tags=["query"])

QUERIES_DIR = config.data_root / "queries"
REPO_QUERIES_DIR = (config.repo_root or Path(__file__).resolve().parents[2]) / "data" / "queries"
DATA_BUCKET_ENV = "DATA_BUCKET"
QUERIES_PREFIX = "queries/"


class Metric(str, Enum):
    VAR = "var"
    META = "meta"
    # Per (owner, ticker) holding metrics (#7380), valued in GBP from the
    # stored ``Close_gbp`` series -- see ``_holding_rows``.
    MARKET_VALUE_GBP = "market_value_gbp"
    GAIN_GBP = "gain_gbp"


HOLDING_METRICS = (Metric.MARKET_VALUE_GBP, Metric.GAIN_GBP)


class CustomQuery(BaseModel):
    start: date
    end: date
    owners: Optional[List[str]] = None
    tickers: Optional[List[str]] = None
    metrics: List[Metric] = Field(default_factory=list)
    name: Optional[str] = None
    format: Optional[str] = Field("json", pattern="^(json|csv|xlsx)$")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# The literal slug of the fixture checked in at data/queries/demo-slug.json.
# Pinned explicitly (not just derived from demo_identity()) because
# config.example.yaml documents demo_identity: steve alongside the
# repo-relative data_root: data default -- i.e. the DOCUMENTED setup
# computes a demo_identity()-derived slug of "steve-slug", which does not
# match this file at all, in exactly the configuration where QUERIES_DIR
# and REPO_QUERIES_DIR coincide and the leak occurs. Filtering only the
# dynamic slug would silently fail to hide the fixture for anyone following
# the documented setup.
_DEMO_SLUG_FIXTURE_FILENAME = "demo-slug"


def _seeded_fixture_slugs() -> set[str]:
    """Slugs for demo/seed query fixtures shipped in the repo (e.g.
    ``data/queries/demo-slug.json``) that must never surface in the
    user-facing "saved queries" list.

    These fixtures live under REPO_QUERIES_DIR, which resolves to the same
    directory as the mutable QUERIES_DIR whenever ``data_root`` is left at
    its repo-relative default (see config.example.yaml). ``list_saved_queries``
    below excludes them from the *listing*; they remain loadable by slug via
    ``_load_query_local``'s REPO_QUERIES_DIR fallback, which
    ``test_custom_query_routes_fallback_to_local`` exercises directly.

    Includes both the pinned literal filename (see
    ``_DEMO_SLUG_FIXTURE_FILENAME`` above) and the slug computed from the
    *configured* demo_identity (lower-cased, matching ``_slugify``'s
    normalisation), so a deployment that renames the identity but keeps
    seeding a matching fixture is still covered.
    """
    return {_DEMO_SLUG_FIXTURE_FILENAME, f"{demo_identity().lower()}-slug"}


def _iter_holdings(q: CustomQuery) -> Iterator[tuple[str, str, dict]]:
    """Yield ``(owner, TICKER, holding)`` for every holding in the query's scope.

    No owners selected means every owner; no tickers selected means every
    ticker those owners hold. Selected tickers *restrict* the result -- they
    are not added on top of the owners' holdings.
    """
    owners_filter = {o.lower() for o in q.owners} if q.owners else None
    tickers_filter = {t.upper() for t in q.tickers} if q.tickers else None
    for pf in list_portfolios():
        owner_slug = (pf.get("owner") or "").lower()
        if owners_filter is not None and owner_slug not in owners_filter:
            continue
        for acct in pf.get("accounts", []):
            for h in acct.get("holdings", []):
                t = (h.get("ticker") or "").upper()
                if t and (tickers_filter is None or t in tickers_filter):
                    yield owner_slug, t, h


def _resolve_tickers(q: CustomQuery) -> List[str]:
    """Tickers for the per-ticker metrics.

    With owners selected: the tickers those owners hold, narrowed to the
    selected tickers if any. With only tickers selected: exactly those, held
    or not (the page lets a share link carry a ticker nobody holds). With
    neither: everything held.
    """
    if q.tickers and not q.owners:
        return sorted({t.upper() for t in q.tickers})
    return sorted({t for _owner, t, _h in _iter_holdings(q)})


_PRICE_LOOKBACK_DAYS = 7


def _gbp_price(ticker: str, holding: dict, on: date) -> float | None:
    """GBP close for ``ticker`` on ``on``, else the latest usable close in the week before.

    The single-day lookup already walks back over a missing day, but a stored
    row with an empty close (e.g. a partial Yahoo bar for the current day)
    stops it there, so step back a day at a time past such rows.
    """
    sym, _, suffix = ticker.partition(".")
    exch = (holding.get("exchange") or suffix or "L").upper()
    if sym == "CASH":
        # Cash is 1.0 per unit of its own currency; only sterling cash is 1.0
        # in GBP, so leave other currencies unvalued rather than wrong.
        return 1.0 if exch == "GBP" else None
    for back in range(_PRICE_LOOKBACK_DAYS + 1):
        price, _src = _get_price_for_date_scaled(sym, exch, on - timedelta(days=back))
        if price is not None:
            return price
    return None


def _owner_transactions(owner: str, cache: dict[str, dict | None]) -> dict | None:
    """``{"transactions": [...]}`` for ``owner`` (all accounts), or ``None`` if there are none."""
    if owner not in cache:
        try:
            cache[owner] = {"transactions": load_transactions(owner)}
        except FileNotFoundError:
            cache[owner] = None
    return cache[owner]


def _range_units(tx: dict | None, ticker: str, units_now: float, q: CustomQuery) -> tuple[float, float | None]:
    """``(units held at q.end, units held at q.start)`` for ``ticker``.

    Both come from replaying ``tx``, but only when that replay is trusted:
    replayed up to *today* it must reproduce the units held now (it is the
    current holdings it is checked against, so today -- not ``q.end`` -- is
    the right anchor). Otherwise the current units stand in for the end of
    the range and the start is unknown (``None``).
    """
    if tx is not None:
        replayed_now = get_units_as_of(tx, ticker, date.today().isoformat())
        if abs(replayed_now - units_now) <= 1e-6 * max(1.0, abs(units_now)):
            end_units = max(get_units_as_of(tx, ticker, q.end.isoformat()), 0.0)
            start_units = max(get_units_as_of(tx, ticker, q.start.isoformat()), 0.0)
            return end_units, start_units
    return units_now, None


_ACQUIRE_TYPES = {"BUY", "PURCHASE", "TRANSFER_IN"}


def _acquisition_value(t: dict, ticker: str, holding: dict, units: float, when: str) -> float | None:
    """GBP an in-range acquisition entered the position at: its recorded amount,
    else (a transfer in carries none) its units at that day's close."""
    if t.get("amount_minor") is not None:
        return abs(float(t["amount_minor"])) / 100
    price = _gbp_price(ticker, holding, date.fromisoformat(when))
    return units * price if price is not None else None


def _range_buy_unit_cost(tx: dict, ticker: str, holding: dict, q: CustomQuery) -> float | None:
    """Average GBP per unit of ``ticker`` acquired inside the range, from ``tx``.

    Buys count at what was paid; a transfer in at the close on its date, as
    if bought then. ``None`` when nothing was acquired in the range or an
    acquisition can't be valued, so the caller falls back to the position's
    pooled average cost.
    """
    start, end = q.start.isoformat(), q.end.isoformat()
    units = paid = 0.0
    for t in tx.get("transactions", []):
        if (t.get("type") or "").upper() not in _ACQUIRE_TYPES or (t.get("ticker") or "").upper() != ticker:
            continue
        when = str(t.get("date") or "")[:10]
        if not start < when <= end:
            continue
        # A one-transaction replay (as_of = its own date, inclusive) reuses
        # get_units_as_of's quantity parsing, including the PP 1e8 scaling.
        t_units = get_units_as_of({"transactions": [t]}, ticker, when)
        value = _acquisition_value(t, ticker, holding, t_units, when)
        if value is None:
            return None
        units += t_units
        paid += value
    return paid / units if units > 0 else None


def _start_value(
    end_units: float, start_units: float | None, start_price: float | None, unit_cost: float | None
) -> float | None:
    """GBP value the position held at ``q.end`` "started" the range at.

    Of those ``end_units``, the ones already held at ``q.start`` count at the
    start-date price; the rest were bought inside the range and count at
    ``unit_cost``, so their gain runs from what was paid, not from a date they
    weren't yet held. Without a trusted replay, every unit counts at the
    start-date price.
    """
    if start_units is None:
        return end_units * start_price if start_price is not None else None
    held = min(start_units, end_units)
    held_value = held * start_price if start_price is not None else None
    if held <= 0:
        held_value = 0.0
    bought = end_units - held
    if bought <= 1e-9:
        return held_value
    return _add_or_none(held_value, bought * unit_cost if unit_cost is not None else None)


def _unit_cost(acc: dict, tx: dict | None, ticker: str, q: CustomQuery) -> float | None:
    """GBP per unit for units bought inside the range: what those buys cost, else the pooled average."""
    paid = _range_buy_unit_cost(tx, ticker, acc["holding"], q) if tx is not None else None
    if paid is not None:
        return paid
    cost, units_now = acc["cost"], acc["units"]
    return cost / units_now if cost is not None and units_now > 0 else None


def _add_or_none(total: float | None, value: float | None) -> float | None:
    return None if total is None or value is None else total + value


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _aggregate_holdings(q: CustomQuery) -> dict[tuple[str, str], dict]:
    """``(owner, ticker) -> {units, cost, holding}`` summed over the owner's accounts."""
    agg: dict[tuple[str, str], dict] = {}
    for owner, ticker, h in _iter_holdings(q):
        acc = agg.setdefault((owner, ticker), {"units": 0.0, "cost": 0.0, "holding": h})
        acc["units"] += float(h.get("units") or 0)
        cost = h.get("cost_basis_gbp")
        acc["cost"] = _add_or_none(acc["cost"], float(cost) if cost is not None else None)
    return agg


def _holding_row(owner: str, ticker: str, acc: dict, q: CustomQuery, tx_cache: dict) -> dict:
    tx = _owner_transactions(owner, tx_cache)
    end_units, start_units = _range_units(tx, ticker, acc["units"], q)
    row: dict = {"owner": owner, "ticker": ticker, "units": round(end_units, 4)}
    end_price = _gbp_price(ticker, acc["holding"], q.end) if end_units > 0 else 0.0
    end_value = end_units * end_price if end_price is not None else None
    if Metric.MARKET_VALUE_GBP in q.metrics:
        row[Metric.MARKET_VALUE_GBP.value] = _round_or_none(end_value)
    if Metric.GAIN_GBP in q.metrics:
        needs_start_price = start_units is None or min(start_units, end_units) > 0
        start_price = _gbp_price(ticker, acc["holding"], q.start) if needs_start_price else None
        unit_cost = _unit_cost(acc, tx if start_units is not None else None, ticker, q)
        start_value = _start_value(end_units, start_units, start_price, unit_cost)
        row["start_value_gbp"] = _round_or_none(start_value)
        gain = None if end_value is None or start_value is None else end_value - start_value
        row[Metric.GAIN_GBP.value] = _round_or_none(gain)
    return row


def _holding_rows(q: CustomQuery) -> List[dict]:
    """One row per (owner, ticker) currently held, summing that owner's accounts.

    ``units`` and the values are for the position held at ``q.end`` (replayed
    from the owner's transactions; the current units when that replay can't
    be trusted). ``gain_gbp`` is that position's gain over the range (see
    ``_start_value``); a sale inside the range is not counted as realised
    gain. A position sold out completely before today has no current holding
    and so no row, even for a range it was held in. Any unpriced component
    leaves the value ``None`` rather than understating it.
    """
    tx_cache: dict[str, dict | None] = {}
    return [
        _holding_row(owner, ticker, acc, q, tx_cache) for (owner, ticker), acc in sorted(_aggregate_holdings(q).items())
    ]


def _save_query_local(slug: str, q: CustomQuery) -> None:
    """Persist a query to the local filesystem.

    *slug* is a URL path segment and is therefore request-derived.  safe_join
    verifies the resolved path stays inside QUERIES_DIR, blocking traversal
    sequences such as ``../``.  A traversal attempt raises HTTP 400 rather than
    404 so callers can distinguish "bad input" from "not found".
    """
    QUERIES_DIR.mkdir(parents=True, exist_ok=True)
    # Guard: slug comes from a URL parameter; safe_join rejects traversal.
    try:
        path = safe_join(QUERIES_DIR, f"{slug}.json")
    except ValueError as exc:
        raise HTTPException(400, "Invalid query slug") from exc
    path.write_text(json.dumps(q.model_dump(), default=str))


def _load_query_local(slug: str) -> dict:
    """Load a query from the local filesystem.

    Checks the mutable QUERIES_DIR first, then falls back to the read-only
    REPO_QUERIES_DIR.  Both lookups go through safe_join so a traversal slug
    (e.g. ``../etc/passwd``) is caught before any file open is attempted.
    """
    # Guard: slug comes from a URL parameter; safe_join rejects traversal.
    try:
        path = safe_join(QUERIES_DIR, f"{slug}.json")
    except ValueError as exc:
        raise HTTPException(404, "Query not found") from exc
    if path.exists():
        return json.loads(path.read_text())

    # Fallback: same guard applied to the read-only repository queries directory.
    try:
        fallback_path = safe_join(REPO_QUERIES_DIR, f"{slug}.json")
    except ValueError as exc:
        raise HTTPException(404, "Query not found") from exc
    if fallback_path.exists():
        return json.loads(fallback_path.read_text())

    raise HTTPException(404, "Query not found")


def _save_query_s3(slug: str, q: CustomQuery) -> None:
    """Persist a query to S3 under ``queries/<slug>.json``."""
    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        raise HTTPException(500, "Missing DATA_BUCKET env var for AWS query saving")
    try:
        import boto3  # type: ignore

        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=f"{QUERIES_PREFIX}{slug}.json",
            Body=json.dumps(q.model_dump(), default=str).encode("utf-8"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(500, f"Failed to write query to S3: {exc}")


def _list_queries_s3() -> List[str]:
    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        return []
    try:
        import boto3  # type: ignore

        s3 = boto3.client("s3")
    except Exception:  # pragma: no cover - defensive
        return []

    slugs: set[str] = set()
    token: str | None = None
    while True:
        params = {"Bucket": bucket, "Prefix": QUERIES_PREFIX}
        if token:
            params["ContinuationToken"] = token
        resp = s3.list_objects_v2(**params)
        for item in resp.get("Contents", []):
            key = item.get("Key", "")
            if key.endswith(".json") and key.startswith(QUERIES_PREFIX):
                slugs.add(Path(key).stem)
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return sorted(slugs)


def _load_query_s3(slug: str) -> dict:
    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        raise HTTPException(404, "Query not found")
    try:
        import boto3  # type: ignore

        obj = boto3.client("s3").get_object(Bucket=bucket, Key=f"{QUERIES_PREFIX}{slug}.json")
        body = obj.get("Body")
        txt = body.read().decode(encoding="utf-8", errors="replace") if body else ""
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(404, "Query not found") from exc
    if not txt:
        raise HTTPException(404, "Query not found")
    return json.loads(txt)


def _ticker_fields(t: str, q: CustomQuery) -> dict:
    """The per-ticker metrics (VaR, security metadata) for ``t``."""
    sym, exch = (t.split(".", 1) + ["L"])[:2]
    fields: dict = {}
    if Metric.VAR in q.metrics:
        df = load_meta_timeseries_range(sym, exch, start_date=q.start, end_date=q.end)
        # VaR from total returns (#9370); return_basis says "price" when the
        # ticker has no stored corporate actions.
        var, basis = compute_var_with_basis(df, ticker=sym, exchange=exch)
        fields[Metric.VAR.value] = var
        fields["return_basis"] = basis
    if Metric.META in q.metrics:
        fields.update(get_security_meta(t) or {})
    return fields


def _query_rows(q: CustomQuery) -> List[dict]:
    """Rows for ``q``: per (owner, ticker) when a holding metric is asked for, else per ticker."""
    if any(m in q.metrics for m in HOLDING_METRICS):
        rows = _holding_rows(q)
    else:
        rows = [{"ticker": t} for t in _resolve_tickers(q)]
    cache: dict[str, dict] = {}
    for row in rows:
        t = row["ticker"]
        if t not in cache:
            cache[t] = _ticker_fields(t, q)
        row.update(cache[t])
    return rows


def _persist_query(slug: str, q: CustomQuery) -> None:
    if config.app_env == "aws":
        try:
            _save_query_s3(slug, q)
            return
        except HTTPException:
            pass
    _save_query_local(slug, q)


def _render(rows: List[dict], fmt: str | None):
    if fmt == "csv":
        return PlainTextResponse(
            pd.DataFrame(rows).to_csv(index=False),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=custom-query.csv"},
        )
    if fmt == "xlsx":
        buf = io.BytesIO()
        pd.DataFrame(rows).to_excel(buf, index=False)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=custom-query.xlsx"},
        )
    return {"results": rows}


@router.post("/run")
def run_query(q: CustomQuery):
    rows = _query_rows(q)
    if q.name:
        _persist_query(_slugify(q.name), q)
    return _render(rows, q.format)


def _csv_list(value: str | None) -> List[str] | None:
    items = [v.strip() for v in (value or "").split(",") if v.strip()]
    return items or None


@router.get("/run")
def run_query_get(
    start: date,
    end: date,
    owners: str | None = None,
    tickers: str | None = None,
    metrics: str | None = None,
    format: str = "json",
):
    """``POST /run`` as a GET with comma-separated lists, so the page's export links can download."""
    try:
        q = CustomQuery(
            start=start,
            end=end,
            owners=_csv_list(owners),
            tickers=_csv_list(tickers),
            metrics=_csv_list(metrics) or [],
            format=format,
        )
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from exc
    return _render(_query_rows(q), q.format)


@router.post("/save")
def save_named_query(q: CustomQuery):
    """Save ``q`` under the slug of its ``name`` (the page's "Save" button)."""
    slug = _slugify(q.name or "")
    if not slug:
        raise HTTPException(400, "A query name is required")
    _persist_query(slug, q)
    return {"id": slug, "saved": slug}


def _format_saved_query(slug: str, payload: dict) -> dict:
    """Normalise persisted query data into an API response."""

    params = dict(payload or {})
    name = params.pop("name", None)
    if not isinstance(name, str) or not name.strip():
        name = slug
    return {"id": slug, "name": name, "params": params}


@router.get("/saved")
def list_saved_queries(detailed: bool | None = Query(None)):
    wants_detailed = True if detailed is None else bool(detailed)
    hidden_slugs = _seeded_fixture_slugs()
    if config.app_env == "aws":
        slugs = [s for s in _list_queries_s3() if s not in hidden_slugs]
        if not wants_detailed:
            return slugs

        entries = []
        for slug in slugs:
            try:
                payload = _load_query_s3(slug)
            except HTTPException:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            entries.append(_format_saved_query(slug, payload))
        return entries

    if not QUERIES_DIR.exists():
        return []

    slugs = [path.stem for path in sorted(QUERIES_DIR.glob("*.json")) if path.stem not in hidden_slugs]
    if not wants_detailed:
        return slugs

    entries = []
    for slug in slugs:
        path = QUERIES_DIR / f"{slug}.json"
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        entries.append(_format_saved_query(slug, payload))
    return entries


@router.get("/{slug}")
def load_query(slug: str):
    if config.app_env == "aws":
        try:
            return _load_query_s3(slug)
        except HTTPException:
            pass
    return _load_query_local(slug)


@router.post("/{slug}")
def save_query(slug: str, q: CustomQuery):
    _persist_query(slug, q)
    return {"saved": slug}
