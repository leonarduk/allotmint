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

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import pandas as pd

from backend.common.holding_utils import BOOK_COST_SUSPECT_SOURCE, enrich_holding
from backend.common.instrument_classification import ASSET_CLASSES, normalise_asset_class
from backend.common.instruments import get_instrument_meta, resolve_instrument_ticker
from backend.config import config
from backend.data_quality import price_scale
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import (
    cache_only,
    has_cached_meta_timeseries,
    list_cached_meta_tickers,
    load_cached_meta_timeseries_full,
)
from backend.timeseries.corporate_actions import SPLIT, load_corporate_actions
from backend.timeseries.quality import (
    DEFAULT_GAP_THRESHOLD_DAYS,
    DEFAULT_OUTLIER_SIGMA,
    DEFAULT_ROLLING_WINDOW,
    compute_quality,
)
from backend.utils.timeseries_helpers import get_scaling_override

logger = logging.getLogger(__name__)

# A cached series is STALE when its last date is older than this many days.
DEFAULT_STALE_SERIES_MAX_AGE_DAYS = 10

_NON_HOLDINGS_FILES = frozenset({"person.json", "settings.json", "approvals.json"})


class IssueType:
    WRONG_EXCHANGE = "WRONG_EXCHANGE"
    UNRESOLVED_TICKER = "UNRESOLVED_TICKER"
    MISSING_SERIES = "MISSING_SERIES"
    STALE_SERIES = "STALE_SERIES"
    # Stale, but outside the scheduled refresh universe: an orphaned cache
    # file (former holding, one-off screener seed, legacy key), not a
    # failing refresh (#8599).
    UNTRACKED_STALE_SERIES = "UNTRACKED_STALE_SERIES"
    GAPS = "GAPS"
    DUPLICATES = "DUPLICATES"
    OUTLIERS = "OUTLIERS"
    MISSING_METADATA = "MISSING_METADATA"
    TICKER_MISMATCH = "TICKER_MISMATCH"
    IMPLAUSIBLE_BOOK_COST = "IMPLAUSIBLE_BOOK_COST"
    # Held instrument whose metadata has no recognised asset class (#9196).
    MISSING_ASSET_CLASS = "MISSING_ASSET_CLASS"
    # Price ~10x/100x wrong: a pence/pounds mix-up or bad scaling override (#7789).
    PRICE_SCALE_SUSPECT = "PRICE_SCALE_SUSPECT"
    # Day-on-day move above a threshold that is not a scale step (#8602).
    LARGE_DAILY_MOVE = "LARGE_DAILY_MOVE"


SEVERITY = {
    IssueType.WRONG_EXCHANGE: "high",
    IssueType.UNRESOLVED_TICKER: "high",
    IssueType.MISSING_SERIES: "medium",
    IssueType.STALE_SERIES: "medium",
    IssueType.UNTRACKED_STALE_SERIES: "low",
    IssueType.GAPS: "medium",
    IssueType.DUPLICATES: "low",
    IssueType.OUTLIERS: "low",
    IssueType.MISSING_METADATA: "low",
    IssueType.TICKER_MISMATCH: "low",
    IssueType.IMPLAUSIBLE_BOOK_COST: "high",
    IssueType.MISSING_ASSET_CLASS: "low",
    IssueType.PRICE_SCALE_SUSPECT: "high",
    IssueType.LARGE_DAILY_MOVE: "low",
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


def _has_positive_book_cost(holding: dict[str, Any]) -> bool:
    try:
        return float(holding.get("cost_basis_gbp") or 0) > 0 and float(holding.get("units") or 0) > 0
    except (TypeError, ValueError):
        return False


def _implausible_book_cost_issue(
    owner: str,
    account: str,
    holding: dict[str, Any],
    ticker: str,
    price_cache: dict[str, float],
) -> DataQualityIssue | None:
    """Flag a booked cost whose implied unit cost is out of band (#8472).

    Reuses ``enrich_holding`` (the single source of truth for the check) on a
    copy of the raw holding inside ``cache_only()`` so no live fetch happens.
    """
    if not _has_positive_book_cost(holding):
        return None
    with cache_only():
        enriched = enrich_holding(holding, date.today(), price_cache)
    if enriched.get("cost_basis_source") != BOOK_COST_SUSPECT_SOURCE:
        return None
    units = float(holding.get("units") or 0)
    book = enriched.get("cost_basis_gbp")
    price = enriched.get("current_price_gbp")
    # book_suspect is only ever set for a positive booked cost and units > 0.
    implied = float(book or 0.0) / units if units > 0 else 0.0
    return DataQualityIssue(
        id=_issue_id(IssueType.IMPLAUSIBLE_BOOK_COST, owner, account, ticker),
        type=IssueType.IMPLAUSIBLE_BOOK_COST,
        severity=SEVERITY[IssueType.IMPLAUSIBLE_BOOK_COST],
        entity=_holding_entity(owner, account, holding),
        description=(
            f"Holding {ticker} has a booked cost of £{book} for {units:g} units "
            f"(implied £{implied:.4f}/unit) against a price of £{price}; "
            f"the gain is hidden until the book cost is corrected."
        ),
        suggested_fix="Check the book cost against the source statement and correct cost_basis_gbp.",
        preview={
            "before": {"cost_basis_gbp": book, "warning": enriched.get("cost_basis_warning")},
            "after": {"cost_basis_gbp": "corrected"},
        },
        fixable=False,
    )


def _missing_asset_class_issue(ticker: str, meta: dict[str, Any]) -> DataQualityIssue | None:
    """Flag a held instrument whose metadata has no recognised asset class.

    Keyed on the instrument, not the holding, so one gap held in several
    accounts is reported once. Values such as "Fund" name a wrapper, not an
    exposure, so they count as missing too (#9196).
    """
    if normalise_asset_class(meta.get("asset_class")) is not None:
        return None
    symbol, _, exchange = ticker.partition(".")
    return DataQualityIssue(
        id=_issue_id(IssueType.MISSING_ASSET_CLASS, symbol, exchange),
        type=IssueType.MISSING_ASSET_CLASS,
        severity=SEVERITY[IssueType.MISSING_ASSET_CLASS],
        entity={"ticker": symbol, "exchange": exchange},
        description=(
            f"Held instrument {ticker} has asset class {meta.get('asset_class')!r}; "
            f"expected one of {', '.join(ASSET_CLASSES)}."
        ),
        suggested_fix=(
            "Run scripts/classify_instruments.py --write, or add the instrument to "
            "instrument_classification_overrides.json."
        ),
        preview={"before": {"asset_class": meta.get("asset_class")}, "after": {"asset_class": "classified"}},
        fixable=False,
    )


def aggregate_holding_issues(
    accounts_root: Path | None = None,
    *,
    instruments_root: Path | None = None,
) -> list[DataQualityIssue]:
    """Detect holdings-side issues: wrong exchange, unresolved ticker, missing
    series, missing asset class, and implausible booked cost."""
    issues: list[DataQualityIssue] = []
    price_cache: dict[str, float] = {}
    for owner, account, holding in iter_holdings(accounts_root):
        ticker = str(holding.get("ticker") or "").strip().upper()
        parsed = _parse_holding_ticker(ticker)
        if parsed is None:
            continue
        book_issue = _implausible_book_cost_issue(owner, account, holding, ticker, price_cache)
        if book_issue is not None:
            issues.append(book_issue)
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

        asset_class_issue = _missing_asset_class_issue(f"{symbol}.{exchange}", meta)
        if asset_class_issue is not None:
            issues.append(asset_class_issue)

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


def _refresh_universe() -> list[str]:
    """Tickers the scheduled price refresh keeps fresh (held + virtual + watched)."""
    # Imported lazily: backend.common.prices pulls in the portfolio loaders.
    from backend.common.prices import refresh_universe

    return refresh_universe()


def _tracked_series_keys(accounts_root: Path | None) -> tuple[set[str], set[str]] | None:
    """Return ``(full_keys, bare_symbols)`` the refresh keeps fresh, or None.

    Unions the refresh job's own universe with the holdings under
    ``accounts_root`` (the request-resolved tree). Tickers without an
    exchange suffix (e.g. ``AV.``) match on symbol so a suffix problem never
    hides a held series as untracked. None means the universe could not be
    determined; callers then treat every series as tracked so a real refresh
    failure is never under-reported.
    """
    try:
        universe = list(_refresh_universe())
        universe.extend(str(h.get("ticker") or "") for _, _, h in iter_holdings(accounts_root))
    except Exception as exc:
        logger.warning(
            "Could not determine the price refresh universe; reporting all stale series as tracked: %s",
            sanitise_log_value(exc),
        )
        return None
    full: set[str] = set()
    bare: set[str] = set()
    for raw in universe:
        symbol, sep, exchange = raw.strip().upper().partition(".")
        if not symbol:
            continue
        if sep and exchange:
            full.add(f"{symbol}.{exchange}")
        else:
            bare.add(symbol)
    return full, bare


def _is_tracked(ticker: str, exchange: str, tracked: tuple[set[str], set[str]] | None) -> bool:
    if tracked is None:
        return True
    full, bare = tracked
    return f"{ticker}.{exchange}".upper() in full or ticker.upper() in bare


def _stale_series_issue(
    ticker: str,
    exchange: str,
    last: date,
    age_days: int,
    tracked: tuple[set[str], set[str]] | None,
) -> DataQualityIssue:
    """Build the stale issue: a failing refresh if tracked, an orphan if not."""
    entity: dict[str, Any] = {"ticker": ticker, "exchange": exchange}
    before = {"last_date": last.isoformat()}
    if not _is_tracked(ticker, exchange, tracked):
        return DataQualityIssue(
            id=_issue_id(IssueType.UNTRACKED_STALE_SERIES, ticker, exchange),
            type=IssueType.UNTRACKED_STALE_SERIES,
            severity=SEVERITY[IssueType.UNTRACKED_STALE_SERIES],
            entity=entity,
            description=(
                f"Series {ticker}.{exchange} last updated {last} ({age_days} days ago). "
                f"It is not held or watched, so no scheduled refresh maintains it."
            ),
            suggested_fix=(
                "Delete the orphaned cache file, or hold/watch the ticker if it should "
                "stay current (check it is not delisted or renamed)."
            ),
            preview={"before": before, "after": {"last_date": "unchanged"}},
            fixable=False,
        )
    return DataQualityIssue(
        id=_issue_id(IssueType.STALE_SERIES, ticker, exchange),
        type=IssueType.STALE_SERIES,
        severity=SEVERITY[IssueType.STALE_SERIES],
        entity=entity,
        description=f"Series {ticker}.{exchange} last updated {last} ({age_days} days ago).",
        suggested_fix="Refetch the series.",
        preview={"before": before, "after": {"last_date": "refetched"}},
        fix_payload={"kind": "refetch", "ticker": ticker, "exchange": exchange},
    )


def _split_dates(ticker: str, exchange: str) -> frozenset[str]:
    """ISO dates of recorded splits, which legitimately move the price."""
    try:
        actions = load_corporate_actions(ticker, exchange)
    except ValueError as exc:
        logger.warning(
            "Could not load corporate actions for %s.%s: %s",
            sanitise_log_value(ticker),
            sanitise_log_value(exchange),
            sanitise_log_value(exc),
        )
        return frozenset()
    if actions.empty:
        return frozenset()
    splits = actions[actions["Action"] == SPLIT]
    return frozenset(pd.to_datetime(splits["Date"]).dt.date.map(date.isoformat))


def _price_ceiling_reason(
    ticker: str, exchange: str, closes: pd.Series, meta: dict[str, Any] | None
) -> tuple[str, dict[str, Any]] | None:
    """Reason + preview when the effective GBP price exceeds its type's ceiling."""
    ceiling = price_scale.plausible_max_gbp_price(exchange, meta)
    if ceiling is None or closes.empty:
        return None
    scale = get_scaling_override(ticker, exchange, None)
    price_gbp = float(closes.iloc[-1]) * scale
    if price_gbp <= ceiling:
        return None
    factor = price_scale.suggested_override_factor(scale)
    reason = (
        f"latest price £{price_gbp:,.2f} is above the £{ceiling:,.0f} plausible for instrument type "
        f"{price_scale.instrument_type(meta)!r} (raw close {closes.iloc[-1]:g} x factor {scale:g})"
    )
    return reason, {"price_gbp": round(price_gbp, 4), "scale": scale, "suggested_factor": factor}


def _price_scale_fix(ticker: str, exchange: str, factor: float | None) -> str:
    if factor is not None:
        return (
            f'Add "{ticker}": {factor:g} under "{exchange}" in data/scaling_overrides.json '
            f"(or correct the instrument currency metadata), then recheck."
        )
    return (
        "Check the instrument's scaling factor and currency metadata, then refetch or edit "
        "any bad points around the flagged dates."
    )


def _price_scale_issue(
    ticker: str,
    exchange: str,
    closes: pd.Series,
    meta: dict[str, Any] | None,
    split_dates: frozenset[str],
) -> DataQualityIssue | None:
    """Flag a price that looks 10x/100x wrong (#7789). Detection only."""
    reasons: list[str] = []
    before: dict[str, Any] = {}
    steps = price_scale.find_scale_steps(closes, exclude_dates=split_dates)
    if steps:
        reasons.append(f"{len(steps)} step change(s) of a power of ten between consecutive closes")
        before["scale_steps"] = price_scale.limit_points(steps)
    ratio = price_scale.trailing_median_ratio(closes)
    factor_limit = price_scale.TRAILING_MEDIAN_FACTOR
    if ratio is not None and (ratio >= factor_limit or ratio <= 1 / factor_limit):
        reasons.append(f"latest close is {ratio:.3g}x its trailing median")
        before["trailing_median_ratio"] = round(ratio, 4)
    ceiling = _price_ceiling_reason(ticker, exchange, closes, meta)
    if ceiling is not None:
        reasons.append(ceiling[0])
        before.update(ceiling[1])
    if not reasons:
        return None
    return DataQualityIssue(
        id=_issue_id(IssueType.PRICE_SCALE_SUSPECT, ticker, exchange),
        type=IssueType.PRICE_SCALE_SUSPECT,
        severity=SEVERITY[IssueType.PRICE_SCALE_SUSPECT],
        entity={"ticker": ticker, "exchange": exchange},
        description=f"{ticker}.{exchange} price looks mis-scaled: " + "; ".join(reasons) + ".",
        suggested_fix=_price_scale_fix(ticker, exchange, before.get("suggested_factor")),
        preview={"before": before, "after": {"price": "rescaled"}},
        fixable=False,
    )


def _large_move_issue(
    ticker: str, exchange: str, closes: pd.Series, threshold: float, split_dates: frozenset[str]
) -> DataQualityIssue | None:
    """Flag day-on-day moves above ``threshold`` with no split on record (#8602)."""
    moves = price_scale.find_large_moves(closes, threshold, exclude_dates=split_dates)
    if not moves:
        return None
    return DataQualityIssue(
        id=_issue_id(IssueType.LARGE_DAILY_MOVE, ticker, exchange),
        type=IssueType.LARGE_DAILY_MOVE,
        severity=SEVERITY[IssueType.LARGE_DAILY_MOVE],
        entity={"ticker": ticker, "exchange": exchange},
        description=(
            f"{len(moves)} day-on-day move(s) over {threshold:.0%} in {ticker}.{exchange} "
            f"with no split on record (latest {moves[-1]['date']})."
        ),
        suggested_fix="Check the flagged dates against another source; edit bad ticks in the Time Series editor.",
        preview={"before": {"moves": price_scale.limit_points(moves)}, "after": {"reviewed": True}},
        fixable=False,
    )


def aggregate_series_issues(
    *,
    stale_max_age_days: int = DEFAULT_STALE_SERIES_MAX_AGE_DAYS,
    gap_threshold_days: int = DEFAULT_GAP_THRESHOLD_DAYS,
    outlier_sigma: float = DEFAULT_OUTLIER_SIGMA,
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    large_move_threshold: float = price_scale.DEFAULT_LARGE_MOVE_THRESHOLD,
    accounts_root: Path | None = None,
) -> list[DataQualityIssue]:
    """Detect timeseries-side issues: stale, gaps, duplicates, outliers,
    missing metadata, ticker/cache-key mismatches, mis-scaled prices and
    large day-on-day moves.

    A stale series is ``STALE_SERIES`` only when the scheduled refresh is
    responsible for it; otherwise it is ``UNTRACKED_STALE_SERIES`` (#8599).
    """
    issues: list[DataQualityIssue] = []
    today = date.today()
    tracked = _tracked_series_keys(accounts_root)
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

        closes = price_scale.close_series(df)
        split_dates = _split_dates(ticker, exchange)
        for detected in (
            _price_scale_issue(ticker, exchange, closes, meta, split_dates),
            _large_move_issue(ticker, exchange, closes, large_move_threshold, split_dates),
        ):
            if detected is not None:
                issues.append(detected)

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
                issues.append(_stale_series_issue(ticker, exchange, last, age_days, tracked))

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
        issues.extend(aggregate_series_issues(accounts_root=accounts_root, **series_kwargs))
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
