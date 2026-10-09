"""Run the data steward against the configured LLM and MCP server, and save the report."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any, Dict, Optional

from backend.chat.mcp_tools_client import mcp_session
from backend.config import Config
from backend.data_steward.llm import BedrockLLM, OpenAICompatLLM, StewardLLM, new_http_client, resolve_provider
from backend.data_steward.runner import StewardLimits, finish_report, new_report, run_steward
from backend.data_steward.store import save_report
from backend.data_steward.tools import McpStewardTools
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)


async def run_and_save(cfg: Config, *, limits: Optional[StewardLimits] = None) -> Dict[str, Any]:
    """One full run; the report is saved whether the run succeeds or fails."""

    limits = limits or StewardLimits.from_env()
    try:
        choice = resolve_provider(cfg)
    except Exception as exc:  # noqa: BLE001 - recorded in the saved report
        report = new_report("unknown", "unknown", limits)
        report["errors"].append({"stage": "setup", "error": f"{type(exc).__name__}: {exc}"})
        return _save(finish_report(report, "error"))
    if not cfg.mcp_server_url:
        report = new_report(choice.provider, choice.model, limits)
        report["errors"].append({"stage": "setup", "error": "MCP_SERVER_URL is not set, so no tools are available."})
        return _save(finish_report(report, "error"))
    try:
        async with AsyncExitStack() as stack:
            session = await stack.enter_async_context(mcp_session(cfg.mcp_server_url))
            llm: StewardLLM
            if choice.provider == "bedrock":
                llm = BedrockLLM(choice.model)
            else:
                client = await stack.enter_async_context(new_http_client(choice))
                llm = OpenAICompatLLM(client, base_url=choice.base_url or "", model=choice.model)
            report = await run_steward(
                llm, McpStewardTools(session), provider=choice.provider, model=choice.model, limits=limits
            )
    except Exception as exc:  # noqa: BLE001 - e.g. the MCP server is unreachable; recorded in the report
        logger.error("Data steward run failed: %s", sanitise_log_value(exc))
        report = new_report(choice.provider, choice.model, limits)
        report["errors"].append({"stage": "connect", "error": f"{type(exc).__name__}: {exc}"})
        report = finish_report(report, "error")
    return _save(report)


def _save(report: Dict[str, Any]) -> Dict[str, Any]:
    save_report(report)
    logger.info(
        "Data steward run %s finished: status=%s investigated=%s",
        sanitise_log_value(report["run_id"]),
        sanitise_log_value(report["status"]),
        sanitise_log_value(report["issues_investigated"]),
    )
    return report
