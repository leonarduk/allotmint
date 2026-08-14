"""Read-write Data Quality Admin endpoints.

Extends the read-only ``/data-quality`` surface with an aggregated issue list
plus preview/fix/batch/dedupe/audit/undo write actions.  Every fix:

  * backs up the affected file (``.bak``, never overwriting an existing one),
  * records an append-only audit entry atomic with the change,
  * goes through the same accounts-store write path as transactions.py for
    holding changes (never direct JSON file mutation).

Read endpoints (``GET /issues``, ``GET /issues/{id}/preview``, ``GET /audit``)
never fetch live data and never mutate state.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.common.accounts_store import LocalAccountsStore
from backend.common.instruments import resolve_instrument_ticker
from backend.data_quality.audit import append_audit, find_audit_entry, read_audit
from backend.data_quality.issues import (
    FIXABLE_TYPES,
    aggregate_issues,
    find_issue,
)
from backend.routes import get_active_user
from backend.routes.transactions import resolve_writable_store
from backend.timeseries.cache import (
    load_cached_meta_timeseries_full,
    load_meta_timeseries,
    meta_timeseries_cache_path,
)

router = APIRouter(prefix="/data-quality", tags=["data-quality-admin"])

_FETCH_DAYS = 3650


class BatchFixRequest(BaseModel):
    issue_ids: list[str] = Field(min_length=1)


def _issue_list(**filters: Any) -> list[dict[str, Any]]:
    """Return the aggregated issue list as plain dicts."""
    issues = aggregate_issues()
    result = []
    for issue in issues:
        item = issue.to_dict()
        if _matches_filters(item, filters):
            result.append(item)
    return result


def _matches_filters(item: dict[str, Any], filters: dict[str, Any]) -> bool:
    issue_type = filters.get("type")
    severity = filters.get("severity")
    owner = filters.get("owner")
    account = filters.get("account")
    ticker = filters.get("ticker")
    entity = item.get("entity") or {}
    if issue_type and item.get("type") != issue_type:
        return False
    if severity and item.get("severity") != severity:
        return False
    if owner and str(entity.get("owner") or "") != owner:
        return False
    if account and str(entity.get("account") or "") != account:
        return False
    if ticker and ticker.upper() not in (
        str(entity.get("ticker") or "").upper(),
        str(entity.get("holding") or "").upper(),
    ):
        return False
    return True


def _backup_path_for(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".bak")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via temp file + rename (fsync'd)."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def _backup_file_if_needed(path: Path) -> Path:
    """Create ``{path}.bak`` from the current content when missing.

    Never overwrites an existing backup so the earliest known-good state is
    preserved (convention from ``scripts/reconcile_holding_tickers.py``).
    Backs up binary files (e.g. parquet) byte-for-byte.
    """
    backup = _backup_path_for(path)
    if not backup.exists() and path.exists():
        data = path.read_bytes()
        backup.parent.mkdir(parents=True, exist_ok=True)
        with backup.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    return backup


def _resolve_writable_accounts_store(request: Request) -> LocalAccountsStore:
    """Return the writable accounts store, refusing demo/global roots."""
    store, _kind = resolve_writable_store(request)
    if getattr(store, "is_global", False):
        raise HTTPException(
            status_code=400,
            detail="Accounts root is the read-only demo dataset; create a writable account first.",
        )
    return store


def _fsync_file(path: Path) -> None:
    """Fsync an already-written file so its content survives a crash."""
    # Windows requires a writable handle for fsync; open r+b rather than rb.
    with path.open("r+b") as fh:
        os.fsync(fh.fileno())


def _atomic_write_parquet(df: Any, path: Path) -> None:
    """Write ``df`` to ``path`` via a temp file + rename, then fsync.

    Mirrors the audit trail's atomic-write pattern: a crash mid-write leaves
    the original cache file untouched instead of a corrupt partial parquet.
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp_path, index=False)
    _fsync_file(tmp_path)
    os.replace(tmp_path, path)


def _normalise_account_file_name(account: str) -> str:
    return account.strip().lower()


def _fix_wrong_exchange(request: Request, payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Correct a holding's ticker through the accounts-store write path."""
    owner = str(payload["owner"])
    account = _normalise_account_file_name(str(payload["account"]))
    holding_ticker = str(payload["holding_ticker"]).upper()
    resolved_ticker = str(payload["resolved_ticker"]).upper()

    store = _resolve_writable_accounts_store(request)
    file_path = Path(store.local_root) / owner / f"{account}.json" if store.local_root else None

    # Backup before any holding write; never overwrite an existing .bak
    # (convention from scripts/reconcile_holding_tickers.py).
    if file_path is not None and file_path.exists():
        _backup_file_if_needed(file_path)

    before_holdings: list[dict[str, Any]] = []
    after_holdings: list[dict[str, Any]] = []
    with store.edit_document(owner, f"{account}.json", default={}, trailing_newline=True) as data:
        holdings = data.setdefault("holdings", [])
        if not isinstance(holdings, list):
            holdings = data["holdings"] = []
        found = False
        for holding in holdings:
            if not isinstance(holding, dict):
                continue
            if str(holding.get("ticker") or "").upper() == holding_ticker:
                before_holdings.append(dict(holding))
                holding["ticker"] = resolved_ticker
                after_holdings.append(dict(holding))
                found = True
        if not found:
            raise HTTPException(
                status_code=409,
                detail=f"Holding {holding_ticker} no longer exists in {owner}/{account}.",
            )

    # Record the audit atomically with the change: if the audit write fails,
    # restore the pre-change file (the .bak taken above) so the mutation is
    # never left unrecorded.
    try:
        entry = append_audit(
            action="wrong_exchange",
            issue_id=str(payload.get("issue_id") or ""),
            entity={"owner": owner, "account": account, "holding": holding_ticker},
            before={"holdings": before_holdings},
            after={"holdings": after_holdings},
            actor=actor,
            extra={"kind": "wrong_exchange", "owner": owner, "account": account},
        )
    except Exception:
        if file_path is not None:
            backup = _backup_path_for(file_path)
            if backup.exists():
                _atomic_write_text(file_path, backup.read_text(encoding="utf-8"))
        raise
    return {"status": "fixed", "ticker": resolved_ticker, "audit_id": entry["id"]}


def _fix_refetch(payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Fetch/refetch a cached meta timeseries (missing/stale/gaps)."""
    ticker = str(payload["ticker"]).upper()
    exchange = str(payload["exchange"]).upper()
    df = load_meta_timeseries(ticker, exchange, days=_FETCH_DAYS)
    entry = append_audit(
        action="refetch",
        issue_id=str(payload.get("issue_id") or ""),
        entity={"ticker": ticker, "exchange": exchange},
        before={"rows": None},
        after={"rows": len(df) if df is not None else 0},
        actor=actor,
        extra={"kind": "refetch", "ticker": ticker, "exchange": exchange},
    )
    return {"status": "fixed", "rows": len(df) if df is not None else 0, "audit_id": entry["id"]}


def _fix_unresolved_ticker(payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Create metadata for a bare symbol (live lookup) then fetch the series."""
    symbol = str(payload["symbol"]).upper()
    exchange = str(payload["exchange"]).upper()
    resolved = resolve_instrument_ticker(symbol, create_missing=True)
    if resolved is None:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to resolve metadata for {symbol} from any source.",
        )
    resolved_symbol, _, resolved_exchange = resolved.partition(".")
    df = load_meta_timeseries(resolved_symbol, resolved_exchange or exchange, days=_FETCH_DAYS)
    entry = append_audit(
        action="unresolved_ticker",
        issue_id=str(payload.get("issue_id") or ""),
        entity={"symbol": symbol, "exchange": exchange},
        before={"metadata": "missing", "series": "missing"},
        after={"metadata": resolved, "series_rows": len(df) if df is not None else 0},
        actor=actor,
        extra={"kind": "unresolved_ticker", "symbol": symbol, "exchange": exchange},
    )
    return {"status": "fixed", "ticker": resolved, "rows": len(df) if df is not None else 0, "audit_id": entry["id"]}


def _fix_dedupe(payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Dedupe a cached series keeping the latest row per date."""
    ticker = str(payload["ticker"]).upper()
    exchange = str(payload["exchange"]).upper()
    cache = meta_timeseries_cache_path(ticker, exchange)
    if cache.startswith("s3://"):
        raise HTTPException(
            status_code=400,
            detail="Dedupe currently supports the local cache only.",
        )
    path = Path(cache)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cached series not found.")
    df = load_cached_meta_timeseries_full(ticker, exchange)
    before_rows = len(df)
    if "Date" not in df.columns:
        raise HTTPException(status_code=400, detail="Cached series has no Date column.")
    deduped = df.drop_duplicates(subset=["Date"], keep="last").sort_values("Date").reset_index(drop=True)
    _backup_file_if_needed(path)
    _atomic_write_parquet(deduped, path)
    # Audit must be atomic with the change: restore the .bak if the audit
    # write fails so the cache is never left mutated without a record.
    try:
        entry = append_audit(
            action="dedupe",
            issue_id=str(payload.get("issue_id") or ""),
            entity={"ticker": ticker, "exchange": exchange},
            before={"rows": before_rows},
            after={"rows": len(deduped)},
            actor=actor,
            extra={"kind": "dedupe", "ticker": ticker, "exchange": exchange},
        )
    except Exception:
        backup = _backup_path_for(path)
        if backup.exists():
            shutil.copy2(backup, path)
        raise
    return {
        "status": "fixed",
        "removed": before_rows - len(deduped),
        "rows": len(deduped),
        "audit_id": entry["id"],
    }


def _fix_missing_metadata(payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Auto-create instrument metadata for a cached pair (live refresh)."""
    ticker = str(payload["ticker"]).upper()
    exchange = str(payload["exchange"]).upper()
    resolved = resolve_instrument_ticker(ticker, exchanges=(exchange,), create_missing=True)
    if resolved is None:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to create metadata for {ticker}.{exchange}.",
        )
    entry = append_audit(
        action="missing_metadata",
        issue_id=str(payload.get("issue_id") or ""),
        entity={"ticker": ticker, "exchange": exchange},
        before={"metadata": "missing"},
        after={"metadata": resolved},
        actor=actor,
        extra={"kind": "missing_metadata", "ticker": ticker, "exchange": exchange},
    )
    return {"status": "fixed", "ticker": resolved, "audit_id": entry["id"]}


def _fix_ticker_mismatch(payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Normalize the cache rows' Ticker column to the cache key."""
    ticker = str(payload["ticker"]).upper()
    exchange = str(payload["exchange"]).upper()
    cache = meta_timeseries_cache_path(ticker, exchange)
    if cache.startswith("s3://"):
        raise HTTPException(
            status_code=400,
            detail="Ticker normalization currently supports the local cache only.",
        )
    path = Path(cache)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cached series not found.")
    df = load_cached_meta_timeseries_full(ticker, exchange)
    before_tickers: list[str] = []
    if "Ticker" in df.columns:
        before_tickers = sorted({str(v).strip().upper() for v in df["Ticker"].dropna().unique()})
        df["Ticker"] = ticker
    _backup_file_if_needed(path)
    _atomic_write_parquet(df, path)
    try:
        entry = append_audit(
            action="ticker_mismatch",
            issue_id=str(payload.get("issue_id") or ""),
            entity={"ticker": ticker, "exchange": exchange},
            before={"tickers": before_tickers},
            after={"tickers": [ticker]},
            actor=actor,
            extra={"kind": "ticker_mismatch", "ticker": ticker, "exchange": exchange},
        )
    except Exception:
        backup = _backup_path_for(path)
        if backup.exists():
            shutil.copy2(backup, path)
        raise
    return {"status": "fixed", "tickers": [ticker], "audit_id": entry["id"]}


def _apply_fix(issue_id: str, request: Request, actor: str | None) -> dict[str, Any]:
    issues = aggregate_issues()
    issue = find_issue(issues, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Unknown issue id: {issue_id}")
    if not issue.fixable or issue.type not in FIXABLE_TYPES:
        raise HTTPException(status_code=409, detail=f"Issue type {issue.type} has no automated fix.")
    payload = dict(issue.fix_payload)
    payload["issue_id"] = issue_id

    kind = payload.get("kind")
    if kind == "wrong_exchange":
        return _fix_wrong_exchange(request, payload, actor)
    if kind == "refetch":
        return _fix_refetch(payload, actor)
    if kind == "unresolved_ticker":
        return _fix_unresolved_ticker(payload, actor)
    if kind == "dedupe":
        return _fix_dedupe(payload, actor)
    if kind == "missing_metadata":
        return _fix_missing_metadata(payload, actor)
    if kind == "ticker_mismatch":
        return _fix_ticker_mismatch(payload, actor)
    raise HTTPException(status_code=409, detail=f"Unsupported fix kind: {kind}")


@router.get("/issues")
async def list_issues(
    type: str | None = Query(None, description="Filter by issue type (WRONG_EXCHANGE, GAPS, ...)"),
    severity: str | None = Query(None, description="Filter by severity: high | medium | low"),
    owner: str | None = Query(None, description="Filter by holding owner"),
    account: str | None = Query(None, description="Filter by holding account"),
    ticker: str | None = Query(None, description="Filter by ticker (series) or holding ticker"),
) -> dict[str, Any]:
    issues = _issue_list(type=type, severity=severity, owner=owner, account=account, ticker=ticker)
    return {"count": len(issues), "issues": issues}


@router.get("/issues/{issue_id}/preview")
async def preview_issue(issue_id: str) -> dict[str, Any]:
    issues = aggregate_issues()
    issue = find_issue(issues, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Unknown issue id: {issue_id}")
    return {
        "id": issue.id,
        "type": issue.type,
        "severity": issue.severity,
        "entity": issue.entity,
        "description": issue.description,
        "suggested_fix": issue.suggested_fix,
        "preview": issue.preview,
        "fixable": issue.fixable,
    }


@router.post("/issues/{issue_id}/fix")
async def fix_issue(
    issue_id: str,
    request: Request,
    user: str | None = Depends(get_active_user),
) -> dict[str, Any]:
    return _apply_fix(issue_id, request, user)


@router.post("/fixes")
async def batch_fix(
    body: BatchFixRequest,
    request: Request,
    user: str | None = Depends(get_active_user),
) -> dict[str, Any]:
    """Apply the same-type fix for every listed issue, reporting per-issue results."""
    results: list[dict[str, Any]] = []
    for issue_id in body.issue_ids:
        try:
            result = _apply_fix(issue_id, request, user)
            results.append({"issue_id": issue_id, **result, "status": "ok"})
        except HTTPException as exc:
            results.append({"issue_id": issue_id, "status": "error", "detail": exc.detail})
    ok = sum(1 for r in results if r["status"] == "ok")
    return {"applied": ok, "failed": len(results) - ok, "results": results}


@router.post("/series/{ticker}/{exchange}/dedupe")
async def dedupe_series(
    ticker: str,
    exchange: str,
    user: str | None = Depends(get_active_user),
) -> dict[str, Any]:
    """Dedupe a cached series directly (keeps the latest row per date)."""
    payload = {
        "kind": "dedupe",
        "ticker": ticker.upper(),
        "exchange": exchange.upper(),
        "issue_id": f"manual:{ticker.upper()}.{exchange.upper()}",
    }
    return _fix_dedupe(payload, user)


@router.get("/audit")
async def list_audit(limit: int | None = Query(None, ge=1, le=1000)) -> dict[str, Any]:
    entries = read_audit(limit=limit)
    return {"count": len(entries), "entries": entries}


@router.post("/audit/{entry_id}/undo")
async def undo_audit(
    entry_id: str,
    request: Request,
    user: str | None = Depends(get_active_user),
) -> dict[str, Any]:
    """Undo a reversible action recorded in the audit trail."""
    entry = find_audit_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown audit entry: {entry_id}")
    kind = (entry.get("extra") or {}).get("kind")

    if kind == "wrong_exchange":
        store = _resolve_writable_accounts_store(request)
        owner = str((entry.get("entity") or {}).get("owner") or "")
        account = _normalise_account_file_name(str((entry.get("entity") or {}).get("account") or ""))
        before = entry.get("before") or {}
        after = entry.get("after") or {}
        before_holdings = before.get("holdings") or []
        after_holdings = after.get("holdings") or []
        # Pair the audit's own before/after snapshots (one holding per fix) and
        # restore by matching the *after* ticker in the live document, so a
        # list reorder or unrelated holding added since the fix cannot misalign.
        restore_map: dict[str, dict[str, Any]] = {}
        for after_holding in after_holdings:
            if not isinstance(after_holding, dict):
                continue
            after_ticker = str(after_holding.get("ticker") or "").upper()
            if not after_ticker:
                continue
            # The matching before snapshot carries the same entity fields but
            # the original ticker; pair by index (audit records one pair per fix).
            index = after_holdings.index(after_holding)
            if index < len(before_holdings) and isinstance(before_holdings[index], dict):
                restore_map[after_ticker] = dict(before_holdings[index])
        with store.edit_document(owner, f"{account}.json", default={}, trailing_newline=True) as data:
            data.setdefault("holdings", [])
            for holding in data["holdings"]:
                if not isinstance(holding, dict):
                    continue
                current = str(holding.get("ticker") or "").upper()
                if current in restore_map:
                    holding.clear()
                    holding.update(restore_map[current])
        append_audit(
            action="undo",
            issue_id=str(entry.get("issue_id") or ""),
            entity=entry.get("entity") or {},
            before={"action": entry.get("action"), "undo_of": entry_id},
            after={"restored": True},
            actor=user,
            extra={"kind": "undo", "undo_of": entry_id},
        )
        return {"status": "undone", "entry_id": entry_id}

    if kind in {"dedupe", "ticker_mismatch"}:
        ticker = str((entry.get("extra") or {}).get("ticker") or "")
        exchange = str((entry.get("extra") or {}).get("exchange") or "")
        cache = meta_timeseries_cache_path(ticker, exchange)
        if cache.startswith("s3://"):
            raise HTTPException(status_code=400, detail="Undo supports the local cache only.")
        path = Path(cache)
        backup = _backup_path_for(path)
        if not backup.exists():
            raise HTTPException(status_code=409, detail="No backup available to restore from.")
        shutil.copy2(backup, path)
        append_audit(
            action="undo",
            issue_id=str(entry.get("issue_id") or ""),
            entity={"ticker": ticker, "exchange": exchange},
            before={"action": entry.get("action"), "undo_of": entry_id},
            after={"restored": True},
            actor=user,
            extra={"kind": "undo", "undo_of": entry_id},
        )
        return {"status": "undone", "entry_id": entry_id}

    raise HTTPException(
        status_code=409,
        detail=f"Action {entry.get('action')!r} is not reversible.",
    )
