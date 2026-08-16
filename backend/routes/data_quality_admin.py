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

import json
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

import backend.data_quality.issues as dq_issues
from backend.common.accounts_store import LocalAccountsStore
from backend.common.authz import ensure_owner_access
from backend.common.errors import AppError
from backend.common.instruments import resolve_instrument_ticker
from backend.config import config
from backend.data_quality.audit import append_audit, find_audit_entry, read_audit
from backend.data_quality.issues import (
    FIXABLE_TYPES,
    DataQualityIssue,
    IssueType,
    aggregate_issues,
    find_issue,
)
from backend.logging_setup import sanitise_log_value
from backend.routes import get_active_user
from backend.routes._accounts import resolve_accounts_root
from backend.routes.transactions import resolve_writable_store
from backend.timeseries.cache import (
    load_cached_meta_timeseries_full,
    load_meta_timeseries,
    meta_timeseries_cache_path,
)

logger = logging.getLogger(__name__)

# Read-only endpoints (issue listing/preview, audit listing) stay reachable
# regardless of ``enable_data_quality_admin`` — the flag only controls the
# write surface. See ``write_router`` below and backend/bootstrap/routers.py.
router = APIRouter(prefix="/data-quality", tags=["data-quality-admin"])

# Mutating endpoints (fix/undo). Registered by backend/bootstrap/routers.py
# only when ``config.enable_data_quality_admin`` is true, so disabling the
# flag actually removes these routes rather than just hiding the SPA tabs
# (#6739) — every route here also owner-scopes via ``ensure_owner_access``
# where it touches a specific owner's holdings.
write_router = APIRouter(prefix="/data-quality", tags=["data-quality-admin"])

_FETCH_DAYS = 3650

# Cache keys and account document components feed directly into filesystem
# paths (``meta_timeseries_cache_path``, ``{accounts_root}/{owner}/{account}.json``)
# and come from URL path params on the manual endpoints, so they are validated
# here rather than being interpolated into a path unchecked (CodeQL
# py/path-injection).
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,49}$")
_EXCHANGE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,49}$")
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")
_ACCOUNT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
# Audit entry ids are ``uuid.uuid4()`` strings (see ``append_audit``), but the
# undo endpoint takes ``entry_id`` straight from the URL path and folds it
# into a cache-snapshot filename (``_fix_snapshot_path``), so it needs the
# same validate-before-path-use treatment as the cache keys above.
_ENTRY_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


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


def _fix_snapshot_path(path: Path, entry_id: str) -> Path:
    """Per-fix backup path keyed by the audit entry id.

    ``{path}.bak`` only ever holds the *earliest* known-good state (it is
    never overwritten), so with multiple fixes applied to the same cache
    file it does not reflect what any one fix actually overwrote. Undo needs
    to restore exactly the state the fix being undone changed, so cache
    fixes additionally snapshot the pre-fix bytes here, keyed by the audit
    entry's own id.
    """
    return path.with_name(path.name + f".undo.{entry_id}")


def _require_path_within(candidate: Path, directory: Path) -> Path:
    """Resolve ``candidate`` and confirm it stays inside ``directory``.

    ``candidate`` is built from filename components (ticker/exchange/entry id)
    that are already regex-validated (``_TICKER_RE``/``_EXCHANGE_RE``/
    ``_ENTRY_ID_RE``), but CodeQL's py/path-injection query does not model
    those custom validators as sanitizers, so it still flags every later use
    of the resulting path. This resolves the path and checks containment
    against the expected directory using ``os.path.realpath``/``commonpath``
    — the pattern CodeQL's own remediation advice recommends — so the query
    can verify the path is safe at the point of use.
    """
    safe_dir = os.path.realpath(str(directory))
    resolved = os.path.realpath(str(candidate))
    if os.path.commonpath([resolved, safe_dir]) != safe_dir:
        raise HTTPException(status_code=400, detail="Invalid path.")
    return Path(resolved)


def _write_fix_snapshot(path: Path, entry_id: str, before_bytes: bytes) -> None:
    """Persist ``before_bytes`` for undo, keyed by this fix's audit entry id.

    Best-effort: the fix itself and its audit record have already succeeded
    by the time this runs, so a failure here only degrades undo (it falls
    back to the earliest ``.bak``) rather than failing the whole request.
    """
    try:
        _atomic_write_bytes(_fix_snapshot_path(path, entry_id), before_bytes)
    except OSError:
        logger.warning(
            "Failed to write per-fix undo snapshot for %s (audit entry %s)",
            sanitise_log_value(path),
            sanitise_log_value(entry_id),
        )


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
    """Return the writable local accounts store, refusing demo/global/S3 roots."""
    store, _kind = resolve_writable_store(request)
    if getattr(store, "is_global", False):
        raise HTTPException(
            status_code=400,
            detail="Accounts root is the read-only demo dataset; create a writable account first.",
        )
    if getattr(store, "local_root", None) is None:
        raise HTTPException(
            status_code=400,
            detail="Data-quality fixes require a local accounts root; S3-backed stores are not supported.",
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


def _validate_cache_key(ticker: str, exchange: str) -> tuple[str, str]:
    """Upper-case and validate a ticker/exchange pair used in cache paths."""
    return _validate_ticker(ticker), _validate_exchange(exchange)


def _validate_entry_id(entry_id: str) -> str:
    """Validate an audit ``entry_id`` used to build a cache-snapshot path."""
    if not _ENTRY_ID_RE.match(entry_id):
        raise HTTPException(status_code=400, detail="Invalid audit entry id.")
    return entry_id


def _validate_ticker(ticker: str) -> str:
    """Upper-case and validate a ticker/symbol used in cache paths."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker/symbol for a cache path: {ticker}",
        )
    return ticker


def _validate_exchange(exchange: str) -> str:
    """Upper-case and validate an exchange code used in cache paths."""
    exchange = exchange.upper()
    if not _EXCHANGE_RE.match(exchange):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid exchange code for a cache path: {exchange}",
        )
    return exchange


def _validate_owner_account(owner: str, account: str) -> tuple[str, str]:
    """Validate an owner/account pair used to locate an accounts document.

    Both values become path components under the accounts root, so they must
    be a single safe component (no separators, no ``..``) even though the
    store's ``safe_join`` would also block escapes — the audit/backup path is
    built here without that guard.
    """
    account = _normalise_account_file_name(account)
    if not _OWNER_RE.match(owner) or not _ACCOUNT_RE.match(account):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid owner/account for an accounts path: {owner!r}/{account!r}",
        )
    return owner, account


def _fix_wrong_exchange(request: Request, payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Correct a holding's ticker through the accounts-store write path."""
    owner = str(payload["owner"])
    account = str(payload["account"])
    holding_ticker = _validate_ticker(str(payload["holding_ticker"]))
    resolved_ticker = _validate_ticker(str(payload["resolved_ticker"]))
    owner, account = _validate_owner_account(owner, account)
    ensure_owner_access(actor, owner, resolve_accounts_root(request))

    store = _resolve_writable_accounts_store(request)
    file_path = Path(store.local_root) / owner / f"{account}.json" if store.local_root else None
    # ``store.edit_document`` below creates the file when missing, so track
    # whether it existed before the edit: if the audit write then fails we
    # must not leave a newly created, unrecorded file behind.
    file_existed = file_path is not None and file_path.exists()

    # Backup before any holding write; never overwrite an existing .bak
    # (convention from scripts/reconcile_holding_tickers.py).
    if file_path is not None and file_existed:
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
    # never left unrecorded.  The backup is restored byte-for-byte (the file
    # may not round-trip through a text encode/decode); a file created by the
    # edit is removed again.  The restore is conditional: it only rewrites the
    # file when it still holds exactly the bytes this fix wrote, so a concurrent
    # edit made between the fix and the audit failure is never clobbered.
    after_bytes = file_path.read_bytes() if file_path is not None and file_path.exists() else None
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
        _rollback_after_audit_failure(file_path, existed=file_existed, expected_bytes=after_bytes)
        raise
    return {"status": "fixed", "ticker": resolved_ticker, "audit_id": entry["id"]}


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` via temp file + rename (fsync'd)."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def _rollback_after_audit_failure(path: Path | None, *, existed: bool, expected_bytes: bytes | None) -> None:
    """Restore ``path`` to its pre-fix state after a failed audit write.

    Cache/fix mutations are applied first and the audit second; if the audit
    write fails the mutation must not survive unrecorded, so the pre-fix file
    is restored byte-for-byte (atomically) or, when the fix created the file,
    the new file is removed.  The restore is conditional: it only rewrites
    ``path`` when the file still contains exactly the bytes this fix produced
    (``expected_bytes``).  If another request has modified the file in the
    meantime, the backup is deliberately left in place — restoring it would
    clobber the concurrent edit — and the caller re-raises the audit error so
    the unrecorded mutation is surfaced rather than silently reverted.
    """
    if path is None:
        return
    if expected_bytes is not None:
        try:
            if path.read_bytes() != expected_bytes:
                return
        except OSError:
            return
    backup = _backup_path_for(path)
    if existed and backup.exists():
        _atomic_write_bytes(path, backup.read_bytes())
    elif not existed and path.exists():
        path.unlink(missing_ok=True)


def _row_count_at(path: Path) -> int:
    """Row count of the parquet file already at ``path``.

    Reads directly from the resolved cache ``path`` rather than re-resolving
    it via ``ticker``/``exchange`` (as ``load_cached_meta_timeseries_full``
    does internally) so the "before" snapshot always reflects the exact file
    this fix is about to overwrite.
    """
    try:
        return len(pd.read_parquet(path))
    except Exception:
        return 0


def _date_bounds(df: Any) -> tuple[Any, Any] | None:
    """Return ``(min date, max date)`` of ``df``'s ``Date`` column, or None."""
    if df is None or df.empty or "Date" not in df.columns:
        return None
    dates = pd.to_datetime(df["Date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return dates.min(), dates.max()


def _series_snapshot_at(path: Path) -> tuple[int, tuple[Any, Any] | None]:
    """Return ``(row count, date bounds)`` of the parquet already at ``path``.

    Row count alone treats "same count, different dates" (e.g. the fetch
    window shifted without covering the actual gap) as no real change;
    comparing the date range too catches that case.
    """
    try:
        df = pd.read_parquet(path)
    except Exception:
        return 0, None
    return len(df), _date_bounds(df)


def _fix_refetch(payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Fetch/refetch a cached meta timeseries (missing/stale/gaps)."""
    ticker, exchange = _validate_cache_key(str(payload["ticker"]), str(payload["exchange"]))
    cache = meta_timeseries_cache_path(ticker, exchange)
    if cache.startswith("s3://"):
        raise HTTPException(
            status_code=400,
            detail="Refetch currently supports the local cache only.",
        )
    path = Path(cache)
    existed = path.exists()
    before_rows = 0
    before_bounds: tuple[Any, Any] | None = None
    if existed:
        _backup_file_if_needed(path)
        before_rows, before_bounds = _series_snapshot_at(path)
    df = load_meta_timeseries(ticker, exchange, days=_FETCH_DAYS)
    # Never report a refetch as fixed (or audit it) when the upstream
    # returned nothing usable: ``load_meta_timeseries`` only persists a
    # non-empty, schema-valid frame, so an empty result leaves the cache
    # untouched and there is no fetched data to record or restore.
    if df is None or df.empty or "Date" not in df.columns:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned no valid data for {ticker}.{exchange}; cache left unchanged.",
        )
    after_bytes = path.read_bytes() if path.exists() else None
    # A refetch that already existed and came back with the same row count
    # *and* date range covered the gap with nothing new (e.g. upstream had
    # no additional data for the missing dates): record it distinctly rather
    # than as a successful ``action="refetch"``, which would misleadingly
    # read as "a change was made" in the audit trail. Row count alone is not
    # enough -- a same-sized fetch with a shifted date range is a real change.
    no_change = existed and before_rows == len(df) and before_bounds == _date_bounds(df)
    try:
        entry = append_audit(
            action="refetch_no_change" if no_change else "refetch",
            issue_id=str(payload.get("issue_id") or ""),
            entity={"ticker": ticker, "exchange": exchange},
            before={"rows": before_rows},
            after={"rows": len(df)},
            actor=actor,
            extra={
                "kind": "refetch",
                "ticker": ticker,
                "exchange": exchange,
                **({"no_change": True} if no_change else {}),
            },
        )
    except Exception:
        _rollback_after_audit_failure(path, existed=existed, expected_bytes=after_bytes)
        raise
    return {
        "status": "no_change" if no_change else "fixed",
        "rows": len(df),
        "audit_id": entry["id"],
    }


def _fix_unresolved_ticker(payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Create metadata for a bare symbol (live lookup) then fetch the series."""
    symbol = str(payload["symbol"]).upper()
    exchange = str(payload["exchange"]).upper()
    symbol, exchange = _validate_cache_key(symbol, exchange)
    resolved = resolve_instrument_ticker(symbol, create_missing=True)
    if resolved is None:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to resolve metadata for {symbol} from any source.",
        )
    resolved_symbol, _, resolved_exchange = resolved.partition(".")
    cache = meta_timeseries_cache_path(resolved_symbol, resolved_exchange or exchange)
    if cache.startswith("s3://"):
        raise HTTPException(
            status_code=400,
            detail="Unresolved-ticker fixes currently support the local cache only.",
        )
    path = Path(cache)
    existed = path.exists()
    before_rows = 0
    if existed:
        _backup_file_if_needed(path)
        before_rows = _row_count_at(path)
    df = load_meta_timeseries(resolved_symbol, resolved_exchange or exchange, days=_FETCH_DAYS)
    # Same guard as ``_fix_refetch``: an empty/broken fetch must not be
    # recorded as a completed fix, and the cache is left untouched.
    if df is None or df.empty or "Date" not in df.columns:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Upstream returned no valid data for "
                f"{resolved_symbol}.{resolved_exchange or exchange}; cache left unchanged."
            ),
        )
    # ``load_meta_timeseries`` persists the fetched frame to ``path`` as a
    # side effect before returning it, so this check cannot prevent a
    # mis-tagged write; it can only surface one after the fact instead of
    # silently reporting success. Preventing the write outright would need
    # ``load_meta_timeseries`` to expose an unpersisted fetch, which it
    # currently does not.
    if "Ticker" in df.columns:
        fetched_tickers = {str(v).strip().upper() for v in df["Ticker"].dropna().unique()}
        expected_ticker = resolved_symbol.upper()
        if fetched_tickers and fetched_tickers != {expected_ticker}:
            # The mismatched frame is already sitting in the cache at this
            # point (see the comment above), so silently raising here would
            # leave it there with zero audit trail explaining why. Record a
            # quarantine entry -- not marked as a successful fix -- so the
            # contamination is at least traceable.
            quarantine_entry = append_audit(
                action="unresolved_ticker_rejected",
                issue_id=str(payload.get("issue_id") or ""),
                entity={"symbol": symbol, "exchange": exchange, "resolved_ticker": resolved},
                before={"metadata": "missing", "series_rows": before_rows},
                after={"tagged_tickers": sorted(fetched_tickers), "series_rows": len(df)},
                actor=actor,
                extra={
                    "kind": "unresolved_ticker_rejected",
                    "ticker": resolved_symbol,
                    "exchange": resolved_exchange or exchange,
                },
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Upstream data for {resolved_symbol}.{resolved_exchange or exchange} is "
                    f"tagged {sorted(fetched_tickers)}, not {expected_ticker!r}; the cache slot "
                    f"now holds this mismatched data (audit entry {quarantine_entry['id']}) and "
                    "was not recorded as a fix."
                ),
            )
    after_bytes = path.read_bytes() if path.exists() else None
    try:
        entry = append_audit(
            action="unresolved_ticker",
            issue_id=str(payload.get("issue_id") or ""),
            entity={"symbol": symbol, "exchange": exchange},
            before={"metadata": "missing", "series_rows": before_rows},
            after={"metadata": resolved, "series_rows": len(df)},
            actor=actor,
            extra={"kind": "unresolved_ticker", "symbol": symbol, "exchange": exchange},
        )
    except Exception:
        _rollback_after_audit_failure(path, existed=existed, expected_bytes=after_bytes)
        raise
    return {"status": "fixed", "ticker": resolved, "rows": len(df), "audit_id": entry["id"]}


def _fix_dedupe(payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Dedupe a cached series keeping the latest row per date."""
    ticker, exchange = _validate_cache_key(str(payload["ticker"]), str(payload["exchange"]))
    cache = meta_timeseries_cache_path(ticker, exchange)
    if cache.startswith("s3://"):
        raise HTTPException(
            status_code=400,
            detail="Dedupe currently supports the local cache only.",
        )
    path = Path(cache)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cached series not found.")
    before_bytes = path.read_bytes()
    df = load_cached_meta_timeseries_full(ticker, exchange)
    before_rows = len(df)
    if "Date" not in df.columns:
        raise HTTPException(status_code=400, detail="Cached series has no Date column.")
    # Normalise Date the way the cache loader does (``_ensure_schema``):
    # mixed tz-aware/naive values are not comparable, so dedupe/sort would
    # raise mid-request.  Coerce to UTC, strip the tz label, and drop rows
    # with unparseable dates (the read path already drops them via
    # ``_ensure_schema``).  An all-invalid series is rejected rather than
    # written back as an empty cache.
    work = df.copy()
    dates = pd.to_datetime(work["Date"], errors="coerce", utc=True).dt.tz_convert(None)
    work["Date"] = dates.astype("datetime64[ms]")
    work = work.dropna(subset=["Date"])
    if work.empty:
        raise HTTPException(
            status_code=502,
            detail=f"Series {ticker}.{exchange} has no valid dates; cache left unchanged.",
        )
    deduped = work.drop_duplicates(subset=["Date"], keep="last").sort_values("Date").reset_index(drop=True)
    _backup_file_if_needed(path)
    _atomic_write_parquet(deduped, path)
    after_bytes = path.read_bytes()
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
        # The cache file is known to exist (404-checked above), so restore
        # it byte-for-byte from the .bak if the audit write failed.
        _rollback_after_audit_failure(path, existed=True, expected_bytes=after_bytes)
        raise
    _write_fix_snapshot(path, entry["id"], before_bytes)
    return {
        "status": "fixed",
        "removed": before_rows - len(deduped),
        "rows": len(deduped),
        "audit_id": entry["id"],
    }


def _fix_missing_metadata(payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Auto-create instrument metadata for a cached pair (live refresh)."""
    ticker, exchange = _validate_cache_key(str(payload["ticker"]), str(payload["exchange"]))
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
    ticker, exchange = _validate_cache_key(str(payload["ticker"]), str(payload["exchange"]))
    cache = meta_timeseries_cache_path(ticker, exchange)
    if cache.startswith("s3://"):
        raise HTTPException(
            status_code=400,
            detail="Ticker normalization currently supports the local cache only.",
        )
    path = Path(cache)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cached series not found.")
    before_bytes = path.read_bytes()
    df = load_cached_meta_timeseries_full(ticker, exchange)
    before_tickers: list[str] = []
    if "Ticker" in df.columns:
        before_tickers = sorted({str(v).strip().upper() for v in df["Ticker"].dropna().unique()})
        df["Ticker"] = ticker
    _backup_file_if_needed(path)
    _atomic_write_parquet(df, path)
    after_bytes = path.read_bytes()
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
        # The cache file is known to exist (404-checked above), so restore
        # it byte-for-byte from the .bak if the audit write failed.
        _rollback_after_audit_failure(path, existed=True, expected_bytes=after_bytes)
        raise
    _write_fix_snapshot(path, entry["id"], before_bytes)
    return {"status": "fixed", "tickers": [ticker], "audit_id": entry["id"]}


def _apply_resolved_fix(issue: DataQualityIssue, request: Request, actor: str | None) -> dict[str, Any]:
    """Dispatch an already-looked-up issue to its fix implementation."""
    if not issue.fixable or issue.type not in FIXABLE_TYPES:
        raise HTTPException(status_code=409, detail=f"Issue type {issue.type} has no automated fix.")
    payload = dict(issue.fix_payload)
    payload["issue_id"] = issue.id

    kind = payload.get("kind")
    if kind == "wrong_exchange":
        return _fix_wrong_exchange(request, payload, actor)
    if kind in ("refetch", "missing_series"):
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


def _apply_fix(issue_id: str, request: Request, actor: str | None) -> dict[str, Any]:
    issues = aggregate_issues()
    issue = find_issue(issues, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Unknown issue id: {issue_id}")
    return _apply_resolved_fix(issue, request, actor)


def _holding_ticker_exists(owner: str, account: str, ticker: str) -> bool:
    """Check a single accounts document for one holding ticker.

    Used to revalidate holdings-based issues per batch item without walking
    the full holdings tree that ``aggregate_issues`` scans (#6741).
    """
    root = getattr(config, "accounts_root", None)
    if root is None:
        return True
    path = Path(root) / owner / f"{_normalise_account_file_name(account)}.json"
    if not path.exists():
        return False
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(document, dict):
        return False
    holdings = document.get("holdings")
    if not isinstance(holdings, list):
        return False
    return any(isinstance(h, dict) and str(h.get("ticker") or "").upper() == ticker.upper() for h in holdings)


def _series_issue_still_applies(issue: DataQualityIssue) -> bool:
    """Re-check one ticker/exchange's current cached-series state.

    Mirrors the single-series checks in ``aggregate_series_issues`` but scoped
    to this issue's own ticker rather than every cached series.
    """
    payload = issue.fix_payload
    ticker = str(payload.get("ticker") or "")
    exchange = str(payload.get("exchange") or "")
    if not ticker or not exchange:
        return True

    if issue.type == IssueType.MISSING_METADATA:
        meta = dq_issues.get_instrument_meta(f"{ticker}.{exchange}")
        return not bool(meta and meta.get("name"))

    try:
        df = dq_issues.load_cached_meta_timeseries_full(ticker, exchange)
    except Exception:
        return True
    if df is None or df.empty:
        return issue.type in (IssueType.STALE_SERIES, IssueType.GAPS)

    if issue.type == IssueType.TICKER_MISMATCH:
        if "Ticker" not in df.columns:
            return False
        row_tickers = {str(v).strip().upper() for v in df["Ticker"].dropna().unique() if str(v).strip()}
        return bool(row_tickers) and row_tickers != {ticker}

    quality = dq_issues.compute_quality(df, ticker, exchange)
    if issue.type == IssueType.DUPLICATES:
        return bool(quality.get("duplicate_dates"))
    if issue.type == IssueType.GAPS:
        return quality.get("gap_count", 0) > 0
    if issue.type == IssueType.STALE_SERIES:
        last_date = quality.get("last_date")
        if last_date is None:
            return True
        last = last_date if isinstance(last_date, date) else date.fromisoformat(str(last_date))
        return (date.today() - last).days > dq_issues.DEFAULT_STALE_SERIES_MAX_AGE_DAYS
    return True


def _issue_still_applies(issue: DataQualityIssue) -> bool:
    """Targeted re-check of just this issue's own entity.

    Batch fix (#6741) aggregates once for the whole request instead of once
    per issue id; this recheck preserves the safety property that an earlier
    fix in the same batch cannot cause a later, now-stale issue to be
    (re)applied, without repeating the full holdings + cached-series scan.
    """
    payload = issue.fix_payload
    kind = payload.get("kind")

    if kind in ("wrong_exchange", "unresolved_ticker"):
        owner = str(payload.get("owner") or issue.entity.get("owner") or "")
        account = str(payload.get("account") or issue.entity.get("account") or "")
        ticker = str(issue.entity.get("holding") or "")
        if not owner or not account or not ticker:
            return True
        return _holding_ticker_exists(owner, account, ticker)

    if kind == "missing_series":
        owner = str(issue.entity.get("owner") or "")
        account = str(issue.entity.get("account") or "")
        holding_ticker = str(issue.entity.get("holding") or "")
        if owner and account and holding_ticker and not _holding_ticker_exists(owner, account, holding_ticker):
            return False
        ticker = str(payload.get("ticker") or "")
        exchange = str(payload.get("exchange") or "")
        if not ticker or not exchange:
            return True
        return not dq_issues.has_cached_meta_timeseries(ticker, exchange)

    return _series_issue_still_applies(issue)


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


@write_router.post("/issues/{issue_id}/fix")
async def fix_issue(
    issue_id: str,
    request: Request,
    user: str | None = Depends(get_active_user),
) -> dict[str, Any]:
    return _apply_fix(issue_id, request, user)


@write_router.post("/fixes")
async def batch_fix(
    body: BatchFixRequest,
    request: Request,
    user: str | None = Depends(get_active_user),
) -> dict[str, Any]:
    """Apply the same-type fix for every listed issue, reporting per-issue results.

    Aggregates issues once for the whole batch rather than once per issue id
    (#6741): the previous version ran a full holdings + cached-series scan
    (``aggregate_issues()``) inside ``_apply_fix`` for every item, so an
    N-issue batch did ~N full scans.  Each item is still individually
    revalidated against its own entity (``_issue_still_applies``) before the
    fix runs, so an issue an earlier item in this same batch already
    resolved is reported as no-longer-applicable instead of being reapplied.

    Catches both ``HTTPException`` (e.g. unknown/unfixable issue) and
    ``AppError`` -- ``ensure_owner_access`` raises ``PermissionDeniedError``
    (an ``AppError``, not an ``HTTPException``) when the caller isn't
    authorized for one issue's owner, and that must be reported as a failed
    item rather than aborting the whole batch and 403ing issues that *were*
    authorized (#6739).
    """
    issues = aggregate_issues()
    by_id = {issue.id: issue for issue in issues}
    results: list[dict[str, Any]] = []
    for issue_id in body.issue_ids:
        issue = by_id.get(issue_id)
        if issue is None:
            results.append({"issue_id": issue_id, "status": "error", "detail": f"Unknown issue id: {issue_id}"})
            continue
        if not _issue_still_applies(issue):
            results.append(
                {
                    "issue_id": issue_id,
                    "status": "error",
                    "detail": "Issue no longer applies; likely resolved earlier in this batch.",
                }
            )
            continue
        try:
            result = _apply_resolved_fix(issue, request, user)
            results.append({"issue_id": issue_id, **result, "status": "ok"})
        except HTTPException as exc:
            results.append({"issue_id": issue_id, "status": "error", "detail": exc.detail})
        except AppError as exc:
            results.append({"issue_id": issue_id, "status": "error", "detail": exc.safe_detail})
    ok = sum(1 for r in results if r["status"] == "ok")
    return {"applied": ok, "failed": len(results) - ok, "results": results}


@write_router.post("/series/{ticker}/{exchange}/dedupe")
async def dedupe_series(
    ticker: str,
    exchange: str,
    user: str | None = Depends(get_active_user),
) -> dict[str, Any]:
    """Dedupe a cached series directly (keeps the latest row per date)."""
    ticker, exchange = _validate_cache_key(ticker, exchange)
    payload = {
        "kind": "dedupe",
        "ticker": ticker,
        "exchange": exchange,
        "issue_id": f"manual:{ticker}.{exchange}",
    }
    return _fix_dedupe(payload, user)


@router.get("/audit")
async def list_audit(limit: int | None = Query(None, ge=1, le=1000)) -> dict[str, Any]:
    entries = read_audit(limit=limit)
    return {"count": len(entries), "entries": entries}


@write_router.post("/audit/{entry_id}/undo")
async def undo_audit(
    entry_id: str,
    request: Request,
    user: str | None = Depends(get_active_user),
) -> dict[str, Any]:
    """Undo a reversible action recorded in the audit trail."""
    entry_id = _validate_entry_id(entry_id)
    entry = find_audit_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown audit entry: {entry_id}")
    kind = (entry.get("extra") or {}).get("kind")

    if kind == "wrong_exchange":
        store = _resolve_writable_accounts_store(request)
        owner = str((entry.get("entity") or {}).get("owner") or "")
        account = str((entry.get("entity") or {}).get("account") or "")
        owner, account = _validate_owner_account(owner, account)
        ensure_owner_access(user, owner, resolve_accounts_root(request))
        # ``store.edit_document`` below creates the file (via ``default={}``)
        # when it is missing, which would silently no-op the undo (nothing to
        # restore in a freshly-created empty document) instead of surfacing
        # that the account file the fix touched no longer exists.
        file_path = Path(store.local_root) / owner / f"{account}.json" if store.local_root else None
        if file_path is None or not file_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Cannot undo: {owner}/{account}.json no longer exists.",
            )
        before = entry.get("before") or {}
        after = entry.get("after") or {}
        before_holdings = before.get("holdings") or []
        after_holdings = after.get("holdings") or []
        # Pair the audit's own before/after snapshots positionally: each
        # after snapshot is the same dict as its before counterpart with the
        # ticker rewritten, so the audit's own list preserves the pairing
        # even when multiple holdings share one ticker.  Restore by matching
        # the *after* ticker in the live document, so a list reorder or
        # unrelated holding added since the fix cannot misalign.
        restore_map: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for before_holding, after_holding in zip(before_holdings, after_holdings):
            if not isinstance(before_holding, dict) or not isinstance(after_holding, dict):
                continue
            after_ticker = str(after_holding.get("ticker") or "").upper()
            if not after_ticker:
                continue
            restore_map[after_ticker] = (dict(before_holding), dict(after_holding))
        with store.edit_document(owner, f"{account}.json", default={}, trailing_newline=True) as data:
            data.setdefault("holdings", [])
            for holding in data["holdings"]:
                if not isinstance(holding, dict):
                    continue
                current = str(holding.get("ticker") or "").upper()
                pair = restore_map.get(current)
                if pair is None:
                    continue
                before_snapshot, after_snapshot = pair
                # Only revert a holding that still matches the state the fix
                # produced; a later manual edit must not be overwritten.
                if holding == after_snapshot:
                    holding.clear()
                    holding.update(before_snapshot)
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
        ticker, exchange = _validate_cache_key(ticker, exchange)
        cache = meta_timeseries_cache_path(ticker, exchange)
        if cache.startswith("s3://"):
            raise HTTPException(status_code=400, detail="Undo supports the local cache only.")
        path = Path(cache)
        # Prefer the snapshot taken for this specific fix (keyed by its audit
        # entry id) over the shared earliest ``.bak``: with multiple fixes
        # applied to the same cache file, the earliest backup predates fixes
        # other than the one being undone. Entries recorded before this
        # snapshot existed fall back to the earliest backup. Both candidates
        # are re-resolved and containment-checked against the cache
        # directory via ``_require_path_within`` before any filesystem use.
        snapshot = _require_path_within(_fix_snapshot_path(path, entry_id), path.parent)
        if snapshot.exists():
            restore_from = snapshot
        else:
            restore_from = _require_path_within(_backup_path_for(path), path.parent)
        if not restore_from.exists():
            raise HTTPException(status_code=409, detail="No backup available to restore from.")
        _atomic_write_bytes(path, restore_from.read_bytes())
        if snapshot.exists():
            snapshot.unlink(missing_ok=True)
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
