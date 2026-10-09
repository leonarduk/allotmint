"""Review queue for fund data proposals (#10482).

The upkeep agents only ever *propose*: a proposal records the value, the public
document it came from (``source_url``) and that document's date. Nothing is
written to instrument metadata until the owner approves it here; approval
writes through the instrument-metadata admin path
(:func:`backend.routes.instrument_admin.update_instrument`, a merge) and
records an audit entry (:mod:`backend.data_quality.audit`) holding the
previous values, so the change can be undone.

Validation reuses the readers the app already trusts: an ongoing charge must
pass :func:`backend.common.fund_charges.ongoing_charge_pct` (so 22 typed for
0.22% is rejected), and a look-through block must pass
:func:`backend.common.look_through.usable_look_through`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlparse

from backend.common.fund_charges import ONGOING_CHARGE_KEY, ongoing_charge_pct
from backend.common.instruments import get_instrument_meta
from backend.common.look_through import usable_look_through
from backend.data_quality.audit import append_audit, find_audit_entry
from backend.fund_upkeep import storage

KIND_ONGOING_CHARGE = "ongoing_charge"
KIND_LOOK_THROUGH = "look_through"
CHARGE_SOURCE_KEY = "ongoing_charge_source"
STATUSES = ("pending", "approved", "rejected", "undone")
_FILE = "proposals.json"


# Fixed texts, so what an API response says about a rejection never comes
# from exception text (CodeQL py/stack-trace-exposure).
REJECTION_REASONS = {
    "source_url": "a proposal needs the http(s) URL of its source document",
    "document_date": "a proposal needs its source document's date (YYYY-MM-DD)",
    "future_date": "the source document's date is in the future",
    "ticker": "a proposal needs a full ticker such as VWRL.L",
    "implausible_charge": "the ongoing charge is not a plausible annual percentage (0-10)",
    "look_through_weights": "a look-through proposal needs country and sector weights",
    "not_json": "the agent's answer was not a JSON object",
    "no_answer": "the agent gave no answer within its step limit",
    "unfetched_source": "the cited source was not fetched during this run",
}


class ProposalRejected(ValueError):
    """A proposed value failed validation and was not queued; ``code`` is a ``REJECTION_REASONS`` key."""

    def __init__(self, code: str) -> None:
        super().__init__(REJECTION_REASONS[code])
        self.code = code


def rejection_reason(code: str) -> str:
    return REJECTION_REASONS.get(code, "the proposal was rejected")


class ProposalStateError(ValueError):
    """The proposal does not exist or is not in a state that allows the action."""


class ProposalNotFound(ProposalStateError):
    """No proposal has that id."""


class ProposalConflict(ValueError):
    """The metadata changed after approval, so undoing would clobber that change."""


def _source(raw: Mapping[str, Any], today: date) -> Dict[str, str]:
    url = str(raw.get("source_url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ProposalRejected("source_url")
    try:
        doc_date = date.fromisoformat(str(raw.get("document_date") or "")[:10])
    except ValueError as exc:
        raise ProposalRejected("document_date") from exc
    if doc_date > today:
        raise ProposalRejected("future_date")
    return {"source_url": url, "document_date": doc_date.isoformat()}


def _ticker(raw: Mapping[str, Any]) -> str:
    ticker = str(raw.get("ticker") or "").strip().upper()
    if "." not in ticker:
        raise ProposalRejected("ticker")
    return ticker


def validate_charge(raw: Mapping[str, Any], *, today: Optional[date] = None) -> Dict[str, Any]:
    """A queued-ready ongoing-charge proposal from ``raw``, or :class:`ProposalRejected`."""
    day = today or date.today()
    value = ongoing_charge_pct({ONGOING_CHARGE_KEY: raw.get(ONGOING_CHARGE_KEY)})
    if value is None:
        raise ProposalRejected("implausible_charge")
    return {
        "kind": KIND_ONGOING_CHARGE,
        "ticker": _ticker(raw),
        "isin": raw.get("isin"),
        "value": value,
        "confidence": raw.get("confidence"),
        **_source(raw, day),
    }


def validate_look_through(raw: Mapping[str, Any], *, today: Optional[date] = None) -> Dict[str, Any]:
    """A queued-ready look-through proposal from ``raw``, or :class:`ProposalRejected`."""
    day = today or date.today()
    source = _source(raw, day)
    block = raw.get("look_through")
    if not isinstance(block, dict) or usable_look_through({"look_through": block}) is None:
        raise ProposalRejected("look_through_weights")
    value = {
        **block,
        "source": block.get("source") or "issuer factsheet",
        "source_url": source["source_url"],
        "as_of": source["document_date"],
        "fetched": day.isoformat(),
    }
    return {"kind": KIND_LOOK_THROUGH, "ticker": _ticker(raw), "isin": raw.get("isin"), "value": value, **source}


def list_proposals(status: Optional[str] = None) -> List[Dict[str, Any]]:
    items = storage.read_json(_FILE, [])
    items = items if isinstance(items, list) else []
    return [p for p in items if status is None or p.get("status") == status]


def add_proposal(proposal: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Queue a validated proposal; ``None`` if one is already pending for that ticker and kind."""
    with storage.LOCK:
        items = list_proposals()
        if any(
            p.get("status") == "pending" and p.get("ticker") == proposal["ticker"] and p.get("kind") == proposal["kind"]
            for p in items
        ):
            return None
        record = {
            **proposal,
            "id": str(uuid.uuid4()),
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        storage.write_json(_FILE, items + [record])
        return record


def _fields(proposal: Mapping[str, Any]) -> Dict[str, Any]:
    """The metadata keys an approval writes."""
    if proposal["kind"] == KIND_LOOK_THROUGH:
        return {"look_through": proposal["value"]}
    return {
        ONGOING_CHARGE_KEY: proposal["value"],
        CHARGE_SOURCE_KEY: {"url": proposal["source_url"], "document_date": proposal["document_date"]},
    }


def _write_meta(ticker: str, fields: Mapping[str, Any]) -> None:
    """Merge ``fields`` into the instrument's metadata via the admin update endpoint."""
    # Imported here: the routes package imports most of the backend at load.
    from backend.routes.instrument_admin import update_instrument

    symbol, exchange = ticker.rsplit(".", 1)
    update_instrument(exchange, symbol, dict(fields))


def _current(ticker: str, keys: List[str]) -> Dict[str, Any]:
    meta = get_instrument_meta(ticker) or {}
    return {key: meta.get(key) for key in keys}


def _decide(proposal_id: str, allowed: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    items = list_proposals()
    proposal = next((p for p in items if p.get("id") == proposal_id), None)
    if proposal is None:
        raise ProposalNotFound("proposal not found")
    if proposal.get("status") != allowed:
        raise ProposalStateError(f"proposal is {proposal.get('status')}, not {allowed}")
    return items, proposal


def _stamp(proposal: Dict[str, Any], status: str, actor: Optional[str]) -> None:
    proposal.update(status=status, decided_by=actor, decided_at=datetime.now(timezone.utc).isoformat())


def approve(proposal_id: str, *, actor: Optional[str] = None) -> Dict[str, Any]:
    """Write a pending proposal to the instrument metadata and audit it."""
    with storage.LOCK:
        items, proposal = _decide(proposal_id, "pending")
        fields = _fields(proposal)
        before = _current(proposal["ticker"], list(fields))
        _write_meta(proposal["ticker"], fields)
        try:
            entry = append_audit(
                action="fund_upkeep_approve",
                issue_id=f"fund-upkeep:{proposal_id}",
                entity={"ticker": proposal["ticker"], "kind": proposal["kind"]},
                before=before,
                after=fields,
                actor=actor,
                extra={"source_url": proposal["source_url"], "document_date": proposal["document_date"]},
            )
        except Exception:
            # Every write is audited: without the entry, put the old values back.
            _write_meta(proposal["ticker"], before)
            raise
        _stamp(proposal, "approved", actor)
        proposal["audit_id"] = entry["id"]
        storage.write_json(_FILE, items)
        return proposal


def reject(proposal_id: str, *, actor: Optional[str] = None) -> Dict[str, Any]:
    with storage.LOCK:
        items, proposal = _decide(proposal_id, "pending")
        _stamp(proposal, "rejected", actor)
        storage.write_json(_FILE, items)
        return proposal


def undo(proposal_id: str, *, actor: Optional[str] = None) -> Dict[str, Any]:
    """Restore the values an approved proposal replaced, with its own audit entry."""
    with storage.LOCK:
        items, proposal = _decide(proposal_id, "approved")
        entry = find_audit_entry(str(proposal.get("audit_id") or ""))
        if entry is None:
            raise ProposalStateError("the approval's audit entry was not found")
        after, before = entry["after"], entry["before"]
        if _current(proposal["ticker"], list(after)) != after:
            raise ProposalConflict("the metadata has changed since this approval; edit it directly instead")
        _write_meta(proposal["ticker"], before)
        undo_entry = append_audit(
            action="fund_upkeep_undo",
            issue_id=f"fund-upkeep:{proposal_id}",
            entity={"ticker": proposal["ticker"], "kind": proposal["kind"]},
            before=after,
            after=before,
            actor=actor,
            extra={"undoes": entry["id"]},
        )
        _stamp(proposal, "undone", actor)
        proposal["undo_audit_id"] = undo_entry["id"]
        storage.write_json(_FILE, items)
        return proposal
