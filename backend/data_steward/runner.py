"""The data steward agent: triage data-quality issues and write a ranked report (#10471).

Phase 1 finds, investigates and reports only. Every tool goes through
``StewardTools``, which only exposes the read-only allowlist
(``backend.chat.tool_switches.DATA_STEWARD_READ_ONLY_TOOLS``), so nothing here can
write data. A "fix available" verdict only *proposes* the app's existing fix
endpoint; a person applies it from the Data Quality page.

A run:

1. reads the open issues (``get_data_quality_report``) and the priced holdings
   (``list_owners`` + ``get_portfolio``), so each issue gets a £/% exposure;
2. keeps issues on held instruments, high severity and largest exposure first, up
   to ``max_issues``;
3. investigates each with the model, at most ``max_tool_calls_per_issue`` tool
   calls, recording every call and result as evidence;
4. checks the verdict (``fix_available`` needs ``fixable``) and adds the proposed
   fix or allowlist reason.

Failures never vanish: a failed step is listed in ``errors`` and a failed issue
gets the verdict ``error``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from backend.data_steward.llm import LLMReply, StewardLLM, estimate_cost_usd
from backend.data_steward.prompt import FINAL_ANSWER_PROMPT, SYSTEM_PROMPT, VERDICTS, issue_brief
from backend.data_steward.tools import StewardTools
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
# Evidence keeps each tool result up to this many characters, so a report stays a
# readable size while still showing what a verdict rests on.
MAX_EVIDENCE_CHARS = 4000
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class StewardLimits:
    max_issues: int = 10
    max_tool_calls_per_issue: int = 6

    @classmethod
    def from_env(cls) -> "StewardLimits":
        return cls(
            max_issues=int(os.getenv("DATA_STEWARD_MAX_ISSUES", cls.max_issues)),
            max_tool_calls_per_issue=int(os.getenv("DATA_STEWARD_MAX_TOOL_CALLS", cls.max_tool_calls_per_issue)),
        )


@dataclass
class Holding:
    owner: str
    account: str
    ticker: str
    value_gbp: float


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_or_raise(text: str, is_error: bool, tool: str) -> Any:
    if is_error:
        raise RuntimeError(f"{tool} failed: {text}")
    return json.loads(text)


# ───────────── holdings and exposure ─────────────


async def load_holdings(tools: StewardTools) -> List[Holding]:
    """Every priced holding across owners, from ``list_owners`` + ``get_portfolio``."""

    owners = _json_or_raise(*await tools.call("list_owners", {}), "list_owners")
    holdings: List[Holding] = []
    for entry in owners:
        owner = str(entry.get("owner") or "")
        if not owner:
            continue
        portfolio = _json_or_raise(*await tools.call("get_portfolio", {"owner": owner}), "get_portfolio")
        for account in portfolio.get("accounts") or []:
            account_name = str(account.get("account_type") or account.get("account") or "")
            for holding in account.get("holdings") or []:
                ticker = str(holding.get("ticker") or "").upper()
                value = holding.get("market_value_gbp")
                if ticker and isinstance(value, (int, float)):
                    holdings.append(Holding(owner, account_name, ticker, float(value)))
    return holdings


def issue_tickers(entity: Dict[str, Any]) -> set[str]:
    """The upper-cased tickers an issue is about, with and without exchange suffix."""

    names = {str(entity.get(key) or "").upper() for key in ("holding", "ticker")}
    if entity.get("ticker") and entity.get("exchange"):
        names.add(f"{entity['ticker']}.{entity['exchange']}".upper())
    names.update(str(t).upper() for t in entity.get("tickers") or [])
    names.discard("")
    return names | {name.rpartition(".")[0] for name in names if "." in name}


def _holding_matches(holding: Holding, entity: Dict[str, Any], tickers: set[str]) -> bool:
    if holding.ticker not in tickers and holding.ticker.rpartition(".")[0] not in tickers:
        return False
    owner, account = entity.get("owner"), entity.get("account")
    if owner and str(owner).lower() != holding.owner.lower():
        return False
    return not account or str(account).lower() == holding.account.lower()


def exposure(entity: Dict[str, Any], holdings: Iterable[Holding], total: float) -> Tuple[float, Optional[float]]:
    """(£ value of the holdings the issue affects, % of the total portfolio)."""

    tickers = issue_tickers(entity)
    value = round(sum(h.value_gbp for h in holdings if _holding_matches(h, entity, tickers)), 2)
    return value, (round(100 * value / total, 2) if total > 0 else None)


def select_issues(
    issues: List[Dict[str, Any]], holdings: Optional[List[Holding]], max_issues: int
) -> Tuple[List[Tuple[Dict[str, Any], Optional[float], Optional[float]]], Dict[str, int]]:
    """Held issues, high severity then largest exposure first, capped at ``max_issues``.

    Without holdings (their lookup failed) nothing can be called unheld, so every
    issue stays in and is ranked by severity alone.
    """

    total = sum(h.value_gbp for h in holdings or [])
    ranked = []
    unheld = 0
    for issue in issues:
        entity = issue.get("entity") or {}
        if holdings is None:
            ranked.append((issue, None, None))
            continue
        value, pct = exposure(entity, holdings, total)
        if value <= 0 and not entity.get("owner"):
            unheld += 1
            continue
        ranked.append((issue, value, pct))
    ranked.sort(key=lambda item: (_SEVERITY_RANK.get(str(item[0].get("severity")), 3), -(item[1] or 0)))
    counts = {
        "issues_held": len(ranked),
        "skipped_unheld": unheld,
        "skipped_over_limit": max(0, len(ranked) - max_issues),
    }
    return ranked[:max_issues], counts


# ───────────── one investigation ─────────────


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0

    def add(self, reply: LLMReply) -> None:
        self.input_tokens += reply.input_tokens
        self.output_tokens += reply.output_tokens


async def _run_tool(tools: StewardTools, name: str, arguments: Dict[str, Any]) -> Tuple[str, bool]:
    try:
        return await tools.call(name, arguments)
    except Exception as exc:  # noqa: BLE001 - shown to the model and kept as evidence
        logger.warning("Data steward tool %s failed: %s", sanitise_log_value(name), sanitise_log_value(exc))
        return f"Tool call failed: {exc}", True


def _evidence(name: str, arguments: Dict[str, Any], text: str, is_error: bool) -> Dict[str, Any]:
    return {
        "tool": name,
        "arguments": arguments,
        "result": text[:MAX_EVIDENCE_CHARS],
        "truncated": len(text) > MAX_EVIDENCE_CHARS,
        "is_error": is_error,
    }


async def investigate(
    llm: StewardLLM,
    tools: StewardTools,
    tool_specs: List[Dict[str, Any]],
    brief: str,
    max_tool_calls: int,
) -> Tuple[str, List[Dict[str, Any]], Usage]:
    """Run the tool loop for one issue; return (final model text, evidence, usage)."""

    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": brief}]
    evidence: List[Dict[str, Any]] = []
    usage = Usage()
    while True:
        budget_left = max_tool_calls - usage.tool_calls
        # Tools stay offered after the budget runs out (Bedrock rejects a history
        # with tool calls but no tool config); further calls are just not run.
        reply = await llm.complete(messages, tool_specs)
        usage.add(reply)
        if not reply.tool_calls or budget_left <= 0:
            return reply.content, evidence, usage
        calls = reply.tool_calls[:budget_left]
        messages.append({"role": "assistant", "content": reply.content, "tool_calls": calls})
        for call in calls:
            text, is_error = await _run_tool(tools, call.name, call.arguments)
            usage.tool_calls += 1
            evidence.append(_evidence(call.name, call.arguments, text, is_error))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": text, "is_error": is_error})
        if usage.tool_calls >= max_tool_calls:
            messages.append({"role": "user", "content": FINAL_ANSWER_PROMPT})


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def parse_verdict(text: str) -> Optional[Dict[str, Any]]:
    """The first JSON object in the model's reply that carries a ``verdict``."""

    text = _THINK_RE.sub("", text or "")
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(value, dict) and "verdict" in value:
            return value
    return None


def _confidence(value: Any) -> Optional[float]:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _str_list(value: Any) -> List[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def fix_proposal(issue: Dict[str, Any]) -> Dict[str, Any]:
    """The existing fix endpoint call a person can apply for ``issue``."""

    issue_id = str(issue["id"])
    return {
        "method": "POST",
        "path": f"/data-quality/issues/{quote(issue_id, safe='')}/fix",
        "issue_id": issue_id,
        "description": issue.get("suggested_fix"),
    }


def build_verdict(issue: Dict[str, Any], text: str) -> Dict[str, Any]:
    """Turn the model's reply into a checked verdict for ``issue``."""

    parsed = parse_verdict(text)
    if parsed is None or parsed.get("verdict") not in VERDICTS:
        return {
            "verdict": "needs_human",
            "root_cause": "undetermined",
            "summary": "The agent did not return a usable verdict; see the evidence and raw reply.",
            "checked": [],
            "unclear": ["No valid verdict JSON in the agent's reply."],
            "confidence": None,
            "raw_reply": (text or "")[:MAX_EVIDENCE_CHARS],
        }
    verdict = {
        "verdict": parsed["verdict"],
        "root_cause": str(parsed.get("root_cause") or "undetermined"),
        "summary": str(parsed.get("summary") or ""),
        "checked": _str_list(parsed.get("checked")),
        "unclear": _str_list(parsed.get("unclear")),
        "confidence": _confidence(parsed.get("confidence")),
    }
    if verdict["verdict"] == "fix_available" and not issue.get("fixable"):
        # Only the app's existing automated fixes count; anything else needs a person.
        verdict["verdict"] = "needs_human"
        verdict["unclear"].append("The agent proposed a fix, but this issue type has no automated fix.")
    if verdict["verdict"] == "fix_available":
        verdict["proposed_fix"] = fix_proposal(issue)
    if verdict["verdict"] == "not_a_problem":
        verdict["allowlist_reason"] = str(parsed.get("allowlist_reason") or verdict["summary"])
    return verdict


# ───────────── the run ─────────────


def _base_item(issue: Dict[str, Any], value: Optional[float], pct: Optional[float]) -> Dict[str, Any]:
    return {
        "issue_id": issue.get("id"),
        "issue_type": issue.get("type"),
        "severity": issue.get("severity"),
        "entity": issue.get("entity") or {},
        "description": issue.get("description"),
        "fixable": bool(issue.get("fixable")),
        "exposure_gbp": value,
        "exposure_pct": pct,
    }


async def _investigate_item(
    llm: StewardLLM,
    tools: StewardTools,
    tool_specs: List[Dict[str, Any]],
    selected: Tuple[Dict[str, Any], Optional[float], Optional[float]],
    limits: StewardLimits,
) -> Tuple[Dict[str, Any], Usage]:
    issue, value, pct = selected
    item = _base_item(issue, value, pct)
    try:
        text, evidence, usage = await investigate(
            llm, tools, tool_specs, issue_brief(issue, value, pct), limits.max_tool_calls_per_issue
        )
    except Exception as exc:  # noqa: BLE001 - reported on the item, the run carries on
        logger.warning(
            "Data steward investigation of %s failed: %s", sanitise_log_value(issue.get("id")), sanitise_log_value(exc)
        )
        item.update({"verdict": "error", "error": f"{type(exc).__name__}: {exc}", "evidence": []})
        return item, Usage()
    item.update(build_verdict(issue, text))
    item["evidence"] = evidence
    item["tokens"] = {"input": usage.input_tokens, "output": usage.output_tokens}
    return item, usage


async def _load_inputs(
    tools: StewardTools, report: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], Optional[List[Holding]]]:
    """Issues (raises when unavailable: nothing to triage) and holdings (None on failure)."""

    dq = _json_or_raise(*await tools.call("get_data_quality_report", {"limit": 500}), "get_data_quality_report")
    report["check_errors"] = dq.get("check_errors") or []
    report["issues_found"] = int(dq.get("total_count") or len(dq.get("issues") or []))
    if dq.get("truncated"):
        report["errors"].append(
            {"stage": "issues", "error": "Issue list truncated at 500; lower-severity issues not seen."}
        )
    try:
        holdings: Optional[List[Holding]] = await load_holdings(tools)
    except Exception as exc:  # noqa: BLE001 - recorded in the report
        report["errors"].append({"stage": "holdings", "error": f"{type(exc).__name__}: {exc}"})
        holdings = None
    report["portfolio_value_gbp"] = None if holdings is None else round(sum(h.value_gbp for h in holdings), 2)
    return list(dq.get("issues") or []), holdings


def new_report(provider: str, model: str, limits: StewardLimits) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(uuid.uuid4()),
        "started_at": _now(),
        "finished_at": None,
        "status": "running",
        "provider": provider,
        "model": model,
        "limits": {"max_issues": limits.max_issues, "max_tool_calls_per_issue": limits.max_tool_calls_per_issue},
        "totals": {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0, "cost_usd": None},
        "portfolio_value_gbp": None,
        "issues_found": 0,
        "issues_held": 0,
        "issues_investigated": 0,
        "skipped_unheld": 0,
        "skipped_over_limit": 0,
        "check_errors": [],
        "errors": [],
        "items": [],
    }


async def run_steward(
    llm: StewardLLM, tools: StewardTools, *, provider: str, model: str, limits: StewardLimits
) -> Dict[str, Any]:
    """Run one triage pass and return the report (not saved; see ``service.run_and_save``)."""

    report = new_report(provider, model, limits)
    try:
        issues, holdings = await _load_inputs(tools, report)
        selected, counts = select_issues(issues, holdings, limits.max_issues)
        report.update(counts)
        tool_specs = await tools.list_tools()
    except Exception as exc:  # noqa: BLE001 - the report carries the failure
        logger.error("Data steward run could not start: %s", sanitise_log_value(exc))
        report["errors"].append({"stage": "setup", "error": f"{type(exc).__name__}: {exc}"})
        return finish_report(report, "error")
    totals = Usage()
    for entry in selected:
        item, usage = await _investigate_item(llm, tools, tool_specs, entry, limits)
        report["items"].append(item)
        totals.input_tokens += usage.input_tokens
        totals.output_tokens += usage.output_tokens
        totals.tool_calls += usage.tool_calls
    report["issues_investigated"] = len(report["items"])
    report["totals"] = {
        "input_tokens": totals.input_tokens,
        "output_tokens": totals.output_tokens,
        "tool_calls": totals.tool_calls,
        "cost_usd": estimate_cost_usd(provider, model, totals.input_tokens, totals.output_tokens),
    }
    failed = report["errors"] or any(item["verdict"] == "error" for item in report["items"])
    return finish_report(report, "partial" if failed else "ok")


def finish_report(report: Dict[str, Any], status: str) -> Dict[str, Any]:
    report["status"] = status
    report["finished_at"] = _now()
    return report
