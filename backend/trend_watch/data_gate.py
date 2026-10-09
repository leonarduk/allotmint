"""The data check every flagged holding passes before it is investigated (#10476).

An unadjusted split or a GBX/GBP flip looks exactly like a collapse, so a holding
with an open data-quality issue in its prices is never reported as deteriorating:
it goes to "data problem, check first" instead. An issue blocks when it is

* a price-series problem (OUTLIERS, ZERO_VOLUME_SPIKE, GAPS, STALE_SERIES,
  pence/pound scaling and the one-day-move checks) -- cost-basis or metadata
  issues do not fake a breakdown;
* graded high or medium severity; and
* within the detector's window: an issue whose dates all fall before the series
  the signals are read from cannot have produced them. An issue that gives no
  dates blocks, except GAPS, which never does: the detector checks for missing
  weeks in its own window instead (:func:`backend.trend_watch.detect.find_artefacts`).

Without the last two conditions every holding with decades of history was
gated by some old gap or a low-severity outlier count, which emptied the list.

The issues come from allotmint-pro's ``get_data_quality_report`` checks when that
package is installed (they add ZERO_VOLUME_SPIKE), and from the app's own
aggregation otherwise. When the data steward (#10471) lands, its verdicts should
replace this list.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.common.core_optional import missing_package
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

BLOCKING_SEVERITIES = frozenset({"high", "medium"})
PRICE_SERIES_TYPES = frozenset(
    {
        "OUTLIERS",
        "ZERO_VOLUME_SPIKE",
        "GAPS",
        "STALE_SERIES",
        "MISSING_SERIES",
        "PRICE_SCALE_SUSPECT",
        "LARGE_DAILY_MOVE",
        "SINGLE_DAY_MOVE_SUSPECT",
    }
)
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

_ARTEFACT_TYPES = {
    "price_scale_step": ("PRICE_SCALE_SUSPECT", "high"),
    "large_one_day_move": ("LARGE_DAILY_MOVE", "medium"),
    "gap": ("GAPS", "medium"),
}


def _entity_tickers(entity: Mapping[str, Any]) -> set[str]:
    names = {str(entity.get(key) or "").upper() for key in ("ticker", "holding")}
    if entity.get("ticker") and entity.get("exchange"):
        names.add(f"{entity['ticker']}.{entity['exchange']}".upper())
    names.update(str(t).upper() for t in entity.get("tickers") or [])
    names.discard("")
    return names


def _matches_ticker(issue: Mapping[str, Any], ticker: str) -> bool:
    wanted = ticker.upper()
    names = _entity_tickers(issue.get("entity") or {})
    if wanted in names:
        return True
    # A bare symbol in the issue (no exchange recorded) still names this line.
    symbol = wanted.rpartition(".")[0] or wanted
    return symbol in names


def latest_date(issue: Mapping[str, Any]) -> Optional[str]:
    """The latest ISO date the issue mentions in its description or preview, if any."""

    text = f"{issue.get('description') or ''} {json.dumps(issue.get('preview') or {}, default=str)}"
    dates = _ISO_DATE.findall(text)
    return max(dates) if dates else None


def _blocks(issue: Mapping[str, Any], since: Optional[str]) -> bool:
    if issue.get("type") not in PRICE_SERIES_TYPES or issue.get("severity") not in BLOCKING_SEVERITIES:
        return False
    if issue.get("type") == "GAPS":
        return False
    latest = latest_date(issue)
    return not (since and latest and latest < since)


def blocking_issues(
    ticker: str, issues: Iterable[Mapping[str, Any]], since: Optional[str] = None
) -> List[Dict[str, Any]]:
    """The open issues for ``ticker`` that stop it being reported as deteriorating.

    ``since`` is the first date of the detector's window (ISO); issues entirely
    before it are ignored.
    """

    return [
        {
            "id": issue.get("id"),
            "type": issue.get("type"),
            "severity": issue.get("severity"),
            "description": issue.get("description"),
            "suggested_fix": issue.get("suggested_fix"),
        }
        for issue in issues
        if _matches_ticker(issue, ticker) and _blocks(issue, since)
    ]


def load_open_issues() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Every open data-quality issue, and any check that failed to run.

    A failed check is returned rather than swallowed, so the report can say
    the data check was incomplete.
    """

    try:
        from allotmint_pro.mcp_server.data_quality_tools import collect_issues
    except ModuleNotFoundError as exc:
        if not missing_package(exc):
            raise
        collect_issues = None
    if collect_issues is not None:
        issues, errors = collect_issues()
        return [dict(issue) for issue in issues], list(errors)

    from backend.data_quality.issues import aggregate_issues

    try:
        return [issue.to_dict() for issue in aggregate_issues()], []
    except Exception as exc:  # noqa: BLE001 - reported in the run's check_errors
        logger.warning("Data quality aggregation failed: %s", sanitise_log_value(exc))
        return [], [{"check": "aggregate_issues", "error": f"{type(exc).__name__}: {exc}"}]


def _artefact_reason(ticker: str, step: Mapping[str, Any]) -> Dict[str, Any]:
    kind = str(step.get("kind"))
    issue_type, severity = _ARTEFACT_TYPES.get(kind, ("LARGE_DAILY_MOVE", "medium"))
    if kind == "gap":
        description = (
            f"{step.get('missing_business_days')} business days of closes are missing from "
            f"{step.get('start')} to {step.get('end')}, inside the window the signals are read from."
        )
        fix = "Refetch the missing range."
    else:
        description = (
            f"Close moved from {step.get('previous')} to {step.get('value')} on {step.get('date')} "
            f"(x{float(step.get('ratio') or 0):.3f}); this looks like an unadjusted split or a "
            "pence/pound change, not trading."
        )
        fix = "Check the series in the Time Series editor and the corporate actions."
    return {
        "id": f"DETECTOR:{kind}:{ticker}:{step.get('date') or step.get('start')}",
        "type": issue_type,
        "severity": severity,
        "description": description,
        "suggested_fix": fix,
    }


def gate(
    ticker: str,
    issues: Sequence[Mapping[str, Any]],
    artefacts: Optional[Sequence[Mapping[str, Any]]] = None,
    since: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Reasons ``ticker`` is a data problem: open issues plus artefacts the detector saw in the series."""

    return blocking_issues(ticker, issues, since) + [_artefact_reason(ticker, step) for step in artefacts or ()]
