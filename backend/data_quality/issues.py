"""Unified data-quality issue aggregation (read-only).

Aggregates holdings, cached timeseries, and instrument metadata into a single
list of typed issues so an admin (or an MCP/AI consumer) can see every problem
and its suggested fix without a CLI or file inspection.

Read path contract (mirrors backend/routes/data_quality.py):
  * No live fetches.  ``resolve_instrument_ticker`` is only ever called with
    ``create_missing=False`` so it consults persisted metadata only.
  * No mutation.  Nothing here writes holdings, metadata, or the cache.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from backend.common.instruments import get_instrument_meta, resolve_instrument_ticker
from backend.config import config
from backend.timeseries.cache import (
    has_cached_meta_timeseries,
    list_cached_meta_tickers,
    load_cached_meta_timeseries_full,
)
from backend.timeseries.quality import (
    DEFAULT_GAP_THRESHOLD_DAYS,
    DEFAULT_OUTLIER_SIGMA,
    DEFAULT_ROLLING_WINDOW,
    compute_quality,
)

# A cached series is STALE when its last date is older than this many days.
DEFAULT_STALE_SERIES_MAX_AGE_DAYS = 10

_NON_HOLDINGS_FILES = frozenset({"person.json", "settings.json", "approvals.json"})


class IssueType:
    WRONG_EXCHANGE = "WRONG_EXCHANGE"
    UNRESOLVED_TICKER = "UNRESOLVED_TICKER"
    MISSING_SERIES = "MISSING_SERIES"
    STALE_SERIES = "STALE_SERIES"
    GAPS = "GAPS"
    DUPLICATES = "DUPLICATES"
    OUTLIERS = "OUTLIERS"
    MISSING_METADATA = "MISSING_METADATA"
    TICKER_MISMATCH = "TICKER_MISMATCH"


SEVERITY = {
    IssueType.WRONG_EXCHANGE: "high",
    IssueType.UNRESOLVED_TICKER: "high",
    IssueType.MISSING_SERIES: "medium",
    IssueType.STALE_SERIES: "medium",
    IssueType.GAPS: "medium",
    IssueType.DUPLICATES: "low",
    IssueType.OUTLIERS: "low",
    IssueType.MISSING_METADATA: "low",
    IssueType.TICKER_MISMATCH: "low",
}

# Issue types whose fix is a fetch/refetch of the cached series.
_FETCH_FIX_TYPES = frozenset(
    {
        IssueType.UNRESOLVED_TICKER,
        IssueType.MISSING_SERIES,
        IssueType.STALE_SERIES,
        IssueType.GAPS,
        IssueType.MISSING_METADATA,
    }
)

# Issue types that have an automated, reversible fix in data_quality_admin.
FIXABLE_TYPES = frozenset(
    {
        IssueType.WRONG_EXCHANGE,
        IssueType.UNRESOLVED_TICKER,
        IssueType.MISSING_SERIES,
        IssueType.STALE_SERIES,
        IssueType.GAPS,
        IssueType.DUPLICATES,
        IssueType.MISSING_METADATA,
        IssueType.TICKER_MISMATCH,
    }
)

_TICKER_RE = re.compile(r"^[A-Z0-9_-]{1,50}$")
_EXCHANGE_RE = re.compile(r"^[A-Z0-9._-]{1,50}$")


@dataclass
class DataQualityIssue:
    """One detected problem with a stable id and a suggested fix."""

    id: str
    type: str
    severity: str
    entity: dict[str, Any]
    description: str
    suggested_fix: str
    preview: dict[str, Any]
    fixable: bool = True
    # Extra structured payload (holding ticker, cache rows, ...) used by the
    # admin route to execute the fix.  Not part of the read contract output.
    fix_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "entity": self.entity,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "preview": self.preview,
            "fixable": self.fixable,
        }


def _validate_symbol(value: str, *, kind: str) -> str:
    upper = value.upper()
    pattern = _TICKER_RE if kind == "ticker" else _EXCHANGE_RE
    if not pattern.match(upper):
        raise ValueError(f"Invalid {kind} format: {value!r}")
    return upper


def _parse_holding_ticker(ticker: str) -> tuple[str, str] | None:
    """Split ``SYM.EX`` into (symbol, exchange); None for CASH or malformed."""
    symbol, sep, exchange = ticker.upper().partition(".")
    if not sep or not symbol or not exchange:
        return None
    if symbol == "CASH":
        return None
    try:
        return _validate_symbol(symbol, kind="ticker"), _validate_symbol(exchange, kind="exchange")
    except ValueError:
        return None


def iter_holdings(accounts_root: Path | None = None) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield ``(owner, account, holding)`` for every holdings document.

    Scans ``{accounts_root}/*/*.json`` skipping metadata/scaffold files
    (person.json, settings.json, approvals.json, *_transactions.json).
    Pure read: never creates owners or writes anything.
    """
    root = accounts_root or getattr(config, "accounts_root", None)
    if root is None or not Path(root).exists():
        return
    for path in sorted(Path(root).glob("*/*.json")):
        if path.name in _NON_HOLDINGS_FILES or path.name.endswith("_transactions.json"):
            continue
        try:
            import json

            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(document, dict):
            continue
        owner = str(document.get("owner") or path.parent.name)
        account = str(document.get("account_type") or path.stem)
        holdings = document.get("holdings")
        if not isinstance(holdings, list):
            continue
        for holding in holdings:
            if isinstance(holding, dict):
                yield owner, account, holding


def _holding_entity(owner: str, account: str, holding: dict[str, Any]) -> dict[str, Any]:
    return {
        "owner": owner,
        "account": account,
        "holding": str(holding.get("ticker") or ""),
    }


def _issue_id(issue_type: str, *parts: str) -> str:
    return ":".join([issue_type, *(p or "" for p in parts)])


def _dedupe_issues(issues: Iterable[DataQualityIssue]) -> list[DataQualityIssue]:
    """Keep the highest-severity issue per id, stable first-seen order."""
    seen: dict[str, DataQualityIssue] = {}
    for issue in issues:
        existing = seen.get(issue.id)
        if existing is None:
            seen[issue.id] = issue
        elif SEVERITY[issue.type] == "high" and SEVERITY[existing.type] != "high":
            seen[issue.id] = issue
    return list(seen.values())


def aggregate_holding_issues(
    accounts_root: Path | None = None,
    *,
    instruments_root: Path | None = None,
) -> list[DataQualityIssue]:
    """Detect holdings-side issues: wrong exchange, unresolved ticker, missing series."""
    issues: list[DataQualityIssue] = []
    for owner, account, holding in iter_holdings(accounts_root):
        ticker = str(holding.get("ticker") or "").strip().upper()
        parsed = _parse_holding_ticker(ticker)
        if parsed is None:
            continue
        symbol, exchange = parsed
        meta = get_instrument_meta(f"{symbol}.{exchange}")
        has_meta = bool(meta and meta.get("name"))
        resolved = resolve_instrument_ticker(symbol, create_missing=False)

        entity = _holding_entity(owner, account, holding)

        if not has_meta:
            if resolved is not None and resolved.upper() != ticker:
                issues.append(
                    DataQualityIssue(
                        id=_issue_id(IssueType.WRONG_EXCHANGE, owner, account, ticker),
                        type=IssueType.WRONG_EXCHANGE,
                        severity=SEVERITY[IssueType.WRONG_EXCHANGE],
                        entity=entity,
                        description=(
                            f"Holding {ticker} has no metadata on {exchange}; " f"instrument resolves to {resolved}."
                        ),
                        suggested_fix=f"Correct holding exchange to {resolved}.",
                        preview={
                            "before": {"ticker": ticker},
                            "after": {"ticker": resolved.upper()},
                        },
                        fix_payload={
                            "kind": "wrong_exchange",
                            "owner": owner,
                            "account": account,
                            "holding_ticker": ticker,
                            "resolved_ticker": resolved.upper(),
                        },
                    )
                )
            else:
                issues.append(
                    DataQualityIssue(
                        id=_issue_id(IssueType.UNRESOLVED_TICKER, owner, account, ticker),
                        type=IssueType.UNRESOLVED_TICKER,
                        severity=SEVERITY[IssueType.UNRESOLVED_TICKER],
                        entity=entity,
                        description=(
                            f"Holding {ticker} has no instrument metadata and the "
                            f"symbol could not be resolved from persisted metadata."
                        ),
                        suggested_fix="Create metadata and fetch the series.",
                        preview={
                            "before": {"metadata": "missing"},
                            "after": {"metadata": "created", "series": "fetched"},
                        },
                        fix_payload={
                            "kind": "unresolved_ticker",
                            "owner": owner,
                            "account": account,
                            "symbol": symbol,
                            "exchange": exchange,
                        },
                    )
                )
            continue

        # Metadata exists; the fix is a missing series on the canonical pair.
        if resolved is not None:
            canonical_ticker = resolved.upper()
            canonical_symbol, canonical_exchange = _parse_holding_ticker(canonical_ticker) or (symbol, exchange)
        else:
            canonical_symbol, canonical_exchange = symbol, exchange
            canonical_ticker = f"{canonical_symbol}.{canonical_exchange}"
        if not has_cached_meta_timeseries(canonical_symbol, canonical_exchange):
            issues.append(
                DataQualityIssue(
                    id=_issue_id(IssueType.MISSING_SERIES, owner, account, canonical_ticker),
                    type=IssueType.MISSING_SERIES,
                    severity=SEVERITY[IssueType.MISSING_SERIES],
                    entity=entity,
                    description=(
                        f"Holding {canonical_ticker} has metadata but no cached "
                        f"timeseries for {canonical_symbol}.{canonical_exchange}."
                    ),
                    suggested_fix="Fetch the series.",
                    preview={
                        "before": {"series": "missing"},
                        "after": {"series": "fetched"},
                    },
                    fix_payload={
                        "kind": "missing_series",
                        "ticker": canonical_symbol,
                        "exchange": canonical_exchange,
                    },
                )
            )
    return _dedupe_issues(issues)


def aggregate_series_issues(
    *,
    stale_max_age_days: int = DEFAULT_STALE_SERIES_MAX_AGE_DAYS,
    gap_threshold_days: int = DEFAULT_GAP_THRESHOLD_DAYS,
    outlier_sigma: float = DEFAULT_OUTLIER_SIGMA,
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
) -> list[DataQualityIssue]:
    """Detect timeseries-side issues: stale, gaps, duplicates, outliers,
    missing metadata, and ticker/cache-key mismatches."""
    issues: list[DataQualityIssue] = []
    today = date.today()
    for ticker, exchange in list_cached_meta_tickers():
        try:
            df = load_cached_meta_timeseries_full(ticker, exchange)
        except Exception:
            continue
        if df is None or df.empty:
            continue

        quality = compute_quality(
            df,
            ticker,
            exchange,
            gap_threshold_days=gap_threshold_days,
            outlier_sigma=outlier_sigma,
            rolling_window=rolling_window,
        )
        meta = get_instrument_meta(f"{ticker}.{exchange}")
        has_meta = bool(meta and meta.get("name"))
        entity: dict[str, Any] = {"ticker": ticker, "exchange": exchange}

        if not has_meta:
            issues.append(
                DataQualityIssue(
                    id=_issue_id(IssueType.MISSING_METADATA, ticker, exchange),
                    type=IssueType.MISSING_METADATA,
                    severity=SEVERITY[IssueType.MISSING_METADATA],
                    entity=entity,
                    description=(f"Cached series {ticker}.{exchange} has no instrument metadata."),
                    suggested_fix="Auto-create metadata via refresh.",
                    preview={
                        "before": {"metadata": "missing"},
                        "after": {"metadata": "created"},
                    },
                    fix_payload={
                        "kind": "missing_metadata",
                        "ticker": ticker,
                        "exchange": exchange,
                    },
                )
            )

        if quality.get("gap_count", 0) > 0:
            issues.append(
                DataQualityIssue(
                    id=_issue_id(IssueType.GAPS, ticker, exchange),
                    type=IssueType.GAPS,
                    severity=SEVERITY[IssueType.GAPS],
                    entity=entity,
                    description=(
                        f"{quality['gap_count']} gap(s) in {ticker}.{exchange} "
                        f"covering {len(quality.get('gaps', []))} period(s)."
                    ),
                    suggested_fix="Refetch / fill the missing range.",
                    preview={
                        "before": {"gap_count": quality["gap_count"]},
                        "after": {"gap_count": 0},
                    },
                    fix_payload={
                        "kind": "refetch",
                        "ticker": ticker,
                        "exchange": exchange,
                    },
                )
            )

        duplicate_dates = quality.get("duplicate_dates", [])
        if duplicate_dates:
            issues.append(
                DataQualityIssue(
                    id=_issue_id(IssueType.DUPLICATES, ticker, exchange),
                    type=IssueType.DUPLICATES,
                    severity=SEVERITY[IssueType.DUPLICATES],
                    entity=entity,
                    description=(f"{len(duplicate_dates)} duplicate date(s) in " f"{ticker}.{exchange} cache."),
                    suggested_fix="Dedupe cache (keep latest row per date).",
                    preview={
                        "before": {"duplicate_dates": duplicate_dates},
                        "after": {"duplicate_dates": []},
                    },
                    fix_payload={
                        "kind": "dedupe",
                        "ticker": ticker,
                        "exchange": exchange,
                    },
                )
            )

        outliers = quality.get("outliers", [])
        if outliers:
            issues.append(
                DataQualityIssue(
                    id=_issue_id(IssueType.OUTLIERS, ticker, exchange),
                    type=IssueType.OUTLIERS,
                    severity=SEVERITY[IssueType.OUTLIERS],
                    entity=entity,
                    description=(f"{len(outliers)} outlier point(s) in {ticker}.{exchange}."),
                    suggested_fix="Review/edit points in the Time Series editor.",
                    preview={
                        "before": {"outliers": outliers},
                        "after": {"reviewed": True},
                    },
                    fixable=False,
                )
            )

        last_date = quality.get("last_date")
        if last_date is not None:
            last = last_date if isinstance(last_date, date) else date.fromisoformat(str(last_date))
            age_days = (today - last).days
            if age_days > stale_max_age_days:
                issues.append(
                    DataQualityIssue(
                        id=_issue_id(IssueType.STALE_SERIES, ticker, exchange),
                        type=IssueType.STALE_SERIES,
                        severity=SEVERITY[IssueType.STALE_SERIES],
                        entity=entity,
                        description=(f"Series {ticker}.{exchange} last updated {last} " f"({age_days} days ago)."),
                        suggested_fix="Refetch the series.",
                        preview={
                            "before": {"last_date": last.isoformat()},
                            "after": {"last_date": "refetched"},
                        },
                        fix_payload={
                            "kind": "refetch",
                            "ticker": ticker,
                            "exchange": exchange,
                        },
                    )
                )

        # Ticker column in the cache rows must match the cache key.
        if "Ticker" in df.columns:
            row_tickers = {str(v).strip().upper() for v in df["Ticker"].dropna().unique() if str(v).strip()}
            if row_tickers and row_tickers != {ticker}:
                issues.append(
                    DataQualityIssue(
                        id=_issue_id(IssueType.TICKER_MISMATCH, ticker, exchange),
                        type=IssueType.TICKER_MISMATCH,
                        severity=SEVERITY[IssueType.TICKER_MISMATCH],
                        entity=entity,
                        description=(
                            f"Cache rows for {ticker}.{exchange} carry ticker "
                            f"value(s) {sorted(row_tickers)} instead of {ticker}."
                        ),
                        suggested_fix="Normalize rows to the cache key.",
                        preview={
                            "before": {"tickers": sorted(row_tickers)},
                            "after": {"tickers": [ticker]},
                        },
                        fix_payload={
                            "kind": "ticker_mismatch",
                            "ticker": ticker,
                            "exchange": exchange,
                        },
                    )
                )
    return issues


def aggregate_issues(
    accounts_root: Path | None = None,
    *,
    include_series: bool = True,
    **series_kwargs: Any,
) -> list[DataQualityIssue]:
    """Aggregate holdings + series issues into one deduplicated list."""
    issues: list[DataQualityIssue] = aggregate_holding_issues(accounts_root)
    if include_series:
        issues.extend(aggregate_series_issues(**series_kwargs))
    return _dedupe_issues(issues)


def find_issue(issues: Sequence[DataQualityIssue], issue_id: str) -> DataQualityIssue | None:
    """Return the issue with ``issue_id`` or None."""
    for issue in issues:
        if issue.id == issue_id:
            return issue
    return None


def writable_accounts_root() -> Path | None:
    """Return the local writable accounts root (None in S3 deployments)."""
    if getattr(config, "app_env", None) == "aws":
        return None
    root = getattr(config, "accounts_root", None)
    return Path(root) if root else None
