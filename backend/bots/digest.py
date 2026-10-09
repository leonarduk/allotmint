"""Compose the bots digest: one ranked list of what needs the owner (#10485).

Deterministic. For one owner it:

1. reads each bot's latest run record through a
   :class:`~backend.bots.run_records.RunRecordSource`;
2. keeps that owner's ``digest_items`` (plus system-wide items for admins),
   and adds one high-severity item per failed run;
3. labels each item **new** or **still open** by ``dedupe_key`` against the
   previous digest, and lists previously open items that disappeared as
   **resolved** (once: a resolved item is not carried into the next digest);
4. ranks by severity, then ``action_required``, then age (oldest first, so a
   long-open item is not buried), capping the number of items per bot;
5. lists every bot's last run state, with "not run yet" for bots with none.

An optional ``opener_fn`` (e.g. an LLM) may write the 2-3 sentence opener from
the composed items. It may only restate them: an opener containing any number
that the items do not contain is rejected and the deterministic opener used.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from backend.bots.digest_models import (
    SEVERITY_RANK,
    BotDescriptor,
    BotRunRecord,
    BotStatus,
    Digest,
    DigestEntry,
    DigestItem,
    DigestPeriod,
    Severity,
)
from backend.bots.run_records import RunRecordSource
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

DEFAULT_PER_BOT_CAP = 5

OpenerFn = Callable[[List[DigestEntry], List[DigestEntry]], str]

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _failure_item(bot: BotDescriptor, record: BotRunRecord, owner: str) -> DigestItem:
    """A failed run is itself a high-severity item (system-wide for system bots)."""

    return DigestItem(
        id=f"{bot.id}:run-failed",
        bot=bot.id,
        owner=None if bot.scope == "system" else owner,
        severity=Severity.HIGH,
        title=f"{bot.name} run failed",
        summary=f"The last run, started {record.started_at.date().isoformat()}, did not complete.",
        action_required=True,
        created=record.started_at,
        dedupe_key=f"{bot.id}:run-failed",
    )


def _visible(item: DigestItem, owner: str, include_system: bool) -> bool:
    if item.owner is None:
        return include_system
    return item.owner == owner


def collect_items(
    bots: Iterable[BotDescriptor],
    records: Dict[str, Optional[BotRunRecord]],
    owner: str,
    include_system: bool,
) -> List[DigestItem]:
    """Every item visible to ``owner`` across the bots' latest runs."""

    items: List[DigestItem] = []
    for bot in bots:
        record = records.get(bot.id)
        if record is None:
            continue
        candidates = list(record.digest_items)
        if record.status == "failed":
            candidates.append(_failure_item(bot, record, owner))
        # Items are attributed to the bot whose run reported them.
        items.extend(item.model_copy(update={"bot": bot.id}) for item in candidates)
    return [item for item in items if _visible(item, owner, include_system)]


def _rank_key(item: DigestItem) -> Tuple[int, bool, datetime, str]:
    return (SEVERITY_RANK[item.severity], not item.action_required, item.created, item.dedupe_key)


def dedupe(items: Iterable[DigestItem]) -> List[DigestItem]:
    """One item per ``dedupe_key``: the highest-ranked one."""

    best: Dict[str, DigestItem] = {}
    for item in items:
        current = best.get(item.dedupe_key)
        if current is None or _rank_key(item) < _rank_key(current):
            best[item.dedupe_key] = item
    return list(best.values())


def rank_and_cap(items: List[DigestEntry], per_bot_cap: int) -> Tuple[List[DigestEntry], Dict[str, int]]:
    """Rank ``items`` and keep at most ``per_bot_cap`` per bot; count what was dropped."""

    kept: List[DigestEntry] = []
    per_bot: Dict[str, int] = {}
    truncated: Dict[str, int] = {}
    for item in sorted(items, key=_rank_key):
        seen = per_bot.get(item.bot, 0)
        if seen >= per_bot_cap:
            truncated[item.bot] = truncated.get(item.bot, 0) + 1
            continue
        per_bot[item.bot] = seen + 1
        kept.append(item)
    return kept, truncated


def label_items(current: List[DigestItem], previous: Optional[Digest]) -> Tuple[List[DigestEntry], List[DigestEntry]]:
    """Return (open entries labelled new/still_open, entries resolved since ``previous``)."""

    previous_open = {entry.dedupe_key: entry for entry in (previous.items if previous else [])}
    previous_keys = set(previous_open) | set(previous.open_keys if previous else [])
    current_keys = {item.dedupe_key for item in current}
    entries = [
        DigestEntry(**item.model_dump(), status="still_open" if item.dedupe_key in previous_keys else "new")
        for item in current
    ]
    resolved = [
        entry.model_copy(update={"status": "resolved"})
        for key, entry in previous_open.items()
        if key not in current_keys
    ]
    return entries, sorted(resolved, key=_rank_key)


def bot_statuses(bots: Iterable[BotDescriptor], records: Dict[str, Optional[BotRunRecord]]) -> List[BotStatus]:
    statuses: List[BotStatus] = []
    for bot in bots:
        record = records.get(bot.id)
        if record is None:
            statuses.append(BotStatus(bot=bot.id, name=bot.name, state="not_run_yet"))
            continue
        statuses.append(
            BotStatus(
                bot=bot.id,
                name=bot.name,
                state=record.status,
                last_run_at=record.started_at,
                summary=record.summary,
            )
        )
    return statuses


def deterministic_opener(items: List[DigestEntry], resolved: List[DigestEntry]) -> str:
    if not items:
        return "Nothing needs you right now."
    new = sum(1 for item in items if item.status == "new")
    high = sum(1 for item in items if item.severity == Severity.HIGH)
    noun = "item needs" if len(items) == 1 else "items need"
    parts = [f"{len(items)} {noun} you ({new} new, {high} high severity)."]
    if resolved:
        parts.append(f"{len(resolved)} resolved since the last digest.")
    return " ".join(parts)


def _numbers(text: str) -> Set[float]:
    return {float(match.replace(",", "")) for match in _NUMBER.findall(text)}


def allowed_numbers(items: List[DigestEntry], resolved: List[DigestEntry]) -> Set[float]:
    """Numbers an opener may use: those in the items' own text, plus counts of the items."""

    allowed: Set[float] = set()
    for item in [*items, *resolved]:
        allowed |= _numbers(f"{item.title} {item.summary}")
    new = sum(1 for item in items if item.status == "new")
    by_severity = [sum(1 for item in items if item.severity == sev) for sev in Severity]
    allowed |= {float(len(items)), float(len(resolved)), float(new), *map(float, by_severity)}
    return allowed


def opener_is_grounded(opener: str, items: List[DigestEntry], resolved: List[DigestEntry]) -> bool:
    """``True`` when every number in ``opener`` comes from the items."""

    return _numbers(opener) <= allowed_numbers(items, resolved)


def write_opener(items: List[DigestEntry], resolved: List[DigestEntry], opener_fn: Optional[OpenerFn]) -> str:
    """The opener: ``opener_fn``'s text if it is grounded, else the deterministic one."""

    fallback = deterministic_opener(items, resolved)
    if opener_fn is None or not items:
        return fallback
    try:
        text = (opener_fn(items, resolved) or "").strip()
    except Exception as exc:
        logger.warning("Digest opener failed; using the plain opener: %s", sanitise_log_value(type(exc).__name__))
        return fallback
    if not text or not opener_is_grounded(text, items, resolved):
        logger.warning("Digest opener rejected (empty or ungrounded); using the plain opener")
        return fallback
    return text


def compose_digest(
    owner: str,
    source: RunRecordSource,
    *,
    previous: Optional[Digest],
    now: datetime,
    include_system: bool = False,
    per_bot_cap: int = DEFAULT_PER_BOT_CAP,
    period: DigestPeriod = "weekly",
    opener_fn: Optional[OpenerFn] = None,
) -> Digest:
    """Compose ``owner``'s digest from the source's latest run records. Writes nothing."""

    bots = source.bots()
    records = {bot.id: source.latest_run(bot.id) for bot in bots}
    current = dedupe(collect_items(bots, records, owner, include_system))
    entries, resolved = label_items(current, previous)
    items, truncated = rank_and_cap(entries, max(1, per_bot_cap))
    return Digest(
        owner=owner,
        period=period,
        generated_at=now,
        opener=write_opener(items, resolved, opener_fn),
        items=items,
        resolved=resolved,
        bots=bot_statuses(bots, records),
        truncated=truncated,
        open_keys=sorted(item.dedupe_key for item in current),
    )


__all__ = [
    "DEFAULT_PER_BOT_CAP",
    "OpenerFn",
    "allowed_numbers",
    "bot_statuses",
    "collect_items",
    "compose_digest",
    "dedupe",
    "deterministic_opener",
    "label_items",
    "opener_is_grounded",
    "rank_and_cap",
    "write_opener",
]
