"""Saved plan-drift briefs (#10475): one history document per owner.

Briefs live at ``<base>/<owner>.json`` as ``{"briefs": [...]}``, oldest
first, capped at :data:`MAX_BRIEFS`. ``<base>`` is ``PLAN_BRIEFS_URI`` when set
(``s3://<bucket>/plan_briefs`` in AWS, so the scheduled Lambda's only write
grant is that prefix) and otherwise ``<data_root>/plan_briefs`` beside the
``plans/`` directory.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

from backend.common.path_utils import safe_join
from backend.common.storage import FileJSONStorage, JSONStorage, S3JSONStorage

PLAN_BRIEFS_DIRNAME = "plan_briefs"
PLAN_BRIEFS_URI_ENV = "PLAN_BRIEFS_URI"
#: Three years of monthly briefs plus on-demand runs.
MAX_BRIEFS = 60

# Same owner-id shape as backend/common/investment_plan.py.
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")


def _storage(owner: str, data_root: Path) -> JSONStorage:
    if not _OWNER_RE.match(owner or ""):
        raise ValueError(f"Invalid owner id {owner!r}")
    uri = os.getenv(PLAN_BRIEFS_URI_ENV, "").strip()
    if uri.startswith("s3://"):
        parsed = urlparse(uri)
        prefix = parsed.path.strip("/")
        return S3JSONStorage(bucket=parsed.netloc, key=f"{prefix}/{owner}.json" if prefix else f"{owner}.json")
    base = Path(uri) if uri else Path(data_root) / PLAN_BRIEFS_DIRNAME
    return FileJSONStorage(safe_join(base, f"{owner}.json"))


def list_briefs(owner: str, data_root: Path) -> list[dict[str, Any]]:
    """Every saved brief for ``owner``, newest first."""
    briefs = _storage(owner, data_root).load().get("briefs") or []
    return [b for b in reversed(briefs) if isinstance(b, dict)]


def latest_brief(owner: str, data_root: Path) -> Optional[dict[str, Any]]:
    briefs = list_briefs(owner, data_root)
    return briefs[0] if briefs else None


def save_brief(owner: str, brief: Mapping[str, Any], data_root: Path) -> None:
    storage = _storage(owner, data_root)
    briefs = [b for b in storage.load().get("briefs") or [] if isinstance(b, dict)]
    briefs.append(dict(brief))
    storage.save({"owner": owner, "briefs": briefs[-MAX_BRIEFS:]})


def brief_summary(brief: Mapping[str, Any]) -> dict[str, Any]:
    """The listing view of a brief: when, and the headline counts."""
    drift = brief.get("drift") or {}
    return {
        "id": brief.get("id"),
        "as_of": brief.get("as_of"),
        "generated_at": brief.get("generated_at"),
        "total_value_gbp": drift.get("total_value_gbp"),
        "out_of_band": drift.get("out_of_band") or [],
        "triggers_fired": sum(1 for t in brief.get("triggers") or [] if t.get("verdict") == "fired"),
        "review_due": bool((brief.get("review") or {}).get("due")),
    }
