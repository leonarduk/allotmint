"""Optional agentic step: ask the chat agent why rows are still unmatched (#10474).

Runs one turn of the configured chat provider over the read-only MCP
data-query tools (``get_transactions``, ``get_instrument``, ``get_account``,
...). It only proposes likely causes; the deterministic diffs stay the
source of truth and nothing is written.
"""

from __future__ import annotations

import json
from typing import List

from backend.chat.providers import run_configured_chat_turn
from backend.config import Config
from backend.reconciliation.models import Diff

EXPLAIN_SYSTEM_PROMPT = (
    "You help reconcile a UK broker statement with a personal investment ledger. "
    "You may only read data with the tools provided. For each unmatched item, give the most "
    "likely cause in one short line (for example: booked on settlement date T+2 instead of trade "
    "date, ticker recorded as BP. instead of BP.L, fee folded into the price, duplicate row). "
    "Do not suggest buying or selling anything and do not give investment advice."
)

# Only these diffs describe a row that failed to pair; cash and unit totals
# follow from them.
_UNMATCHED_KINDS = frozenset({"missing_from_ledger", "missing_from_statement", "amount_mismatch", "fee_mismatch"})


def unmatched(diffs: List[Diff]) -> List[Diff]:
    return [diff for diff in diffs if diff.kind in _UNMATCHED_KINDS]


def build_prompt(owner: str, account: str, diffs: List[Diff]) -> str:
    items = [
        {
            "kind": diff.kind,
            "date": diff.date.isoformat() if diff.date else None,
            "ticker": diff.ticker,
            "ledger_id": diff.ledger_id,
            "detail": diff.message,
        }
        for diff in diffs
    ]
    return (
        f"Owner: {owner}. Account: {account}.\n"
        "These statement/ledger items did not match. Look up the ledger as needed and explain each:\n"
        f"{json.dumps(items, indent=1)}"
    )


async def explain_unmatched(owner: str, account: str, diffs: List[Diff], cfg: Config) -> str | None:
    """Return the agent's explanation, or ``None`` when there is nothing unmatched."""
    items = unmatched(diffs)
    if not items:
        return None
    if not cfg.mcp_server_url:
        raise RuntimeError("MCP_SERVER_URL is not configured, so unmatched rows cannot be explained")
    return await run_configured_chat_turn(
        build_prompt(owner, account, items),
        [],
        cfg=cfg,
        mcp_server_url=cfg.mcp_server_url,
        system_prompt=EXPLAIN_SYSTEM_PROMPT,
    )
