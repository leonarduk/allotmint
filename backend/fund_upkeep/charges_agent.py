"""Find a held fund's ongoing charge (OCF/TER) in its public KIID/factsheet (#10482).

A small tool-calling loop: the model may search the web by ISIN, fetch a
public document and read the instrument's stored metadata -- all read-only
(``READ_ONLY_TOOLS``; a test asserts no write tool is ever offered). Its final
answer is only a *proposal*: it must cite a document the loop actually
fetched, carry the document's date and pass the same plausibility check the
charges view uses, and is then queued for the owner (see :mod:`.proposals`).

Licensing stays as :mod:`backend.common.fund_charges` describes: no
third-party OCF feed. The agent reads one public issuer document per fund,
sends no cookies or credentials, and refuses non-public hosts.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional
from urllib.parse import urlparse

import httpx
import requests

from backend.common.fund_charges import ONGOING_CHARGE_KEY, ongoing_charge_pct
from backend.common.instruments import get_instrument_meta
from backend.config import Config
from backend.fund_upkeep import proposals
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# Assistant message in OpenAI chat-completions shape: {"content", "tool_calls"}.
LlmStep = Callable[[List[Dict[str, Any]], List[Dict[str, Any]]], Dict[str, Any]]

MAX_STEPS = 8
MAX_DOCUMENT_BYTES = 3_000_000
MAX_TEXT_CHARS = 20_000
REQUEST_TIMEOUT_S = 20
BRAVE_KEY_ENV = "ALLOTMINT_MCP_BRAVE_API_KEY"
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
CHARGE_MAX_AGE_DAYS = 365

SYSTEM_PROMPT = (
    "You find the ongoing charges figure (OCF or TER) of one fund from its issuer's public "
    "KIID, KID or factsheet. Search by ISIN and prefer the issuer's own website. Never use "
    "pages that need a login, and never use paid data feeds. Fetch the document before "
    "quoting it. When done, reply with JSON only: "
    '{"ongoing_charge_pct": <percent per year, e.g. 0.22 for 0.22%>, "source_url": '
    '"<the document URL you fetched>", "document_date": "YYYY-MM-DD", "confidence": '
    '"high"|"medium"|"low"} or, if you cannot find it, {"not_found": "<reason>"}.'
)


def _spec(name: str, description: str, properties: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(properties)},
        },
    }


_TICKER_ARG = {"ticker": {"type": "string", "description": "Full ticker, e.g. VWRL.L"}}
TOOL_SPECS: List[Dict[str, Any]] = [
    _spec("get_instrument", "Stored metadata of the instrument (name, ISIN, current charge).", _TICKER_ARG),
    _spec("get_fund_facts", "Stored fund facts of the instrument (index, issuer, etc.).", _TICKER_ARG),
    _spec("search_web", "Search the public web; returns titles, URLs and snippets.", {"query": {"type": "string"}}),
    _spec(
        "fetch_document",
        "Read a public web page or PDF (KIID/factsheet) as text. No logins.",
        {"url": {"type": "string"}},
    ),
]
READ_ONLY_TOOLS = frozenset(spec["function"]["name"] for spec in TOOL_SPECS)


def _public_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        return False
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def _html_text(content: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ")


def _pdf_text(content: bytes) -> str:
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("PDF reading is not available on this server") from exc
    reader = PdfReader(BytesIO(content))
    return " ".join(page.extract_text() or "" for page in reader.pages[:6])


class ReadOnlyToolbox:
    """The agent's tools. Every one reads; none can change stored data."""

    def __init__(self, session: Optional[requests.Session] = None, brave_api_key: Optional[str] = None) -> None:
        self._session = session or requests.Session()
        self._brave_key = brave_api_key if brave_api_key is not None else os.getenv(BRAVE_KEY_ENV)
        self.fetched_urls: set[str] = set()

    def call(self, name: str, arguments: Mapping[str, Any]) -> str:
        if name not in READ_ONLY_TOOLS:
            raise ValueError(f"tool {name!r} is not allowed")
        handler = getattr(self, name)
        return handler(**{key: str(arguments.get(key) or "") for key in ("ticker", "query", "url") if key in arguments})

    def get_instrument(self, ticker: str) -> str:
        meta = get_instrument_meta(ticker.upper()) or {}
        keys = ("ticker", "name", "isin", "instrumentType", "currency", ONGOING_CHARGE_KEY, proposals.CHARGE_SOURCE_KEY)
        return json.dumps({key: meta.get(key) for key in keys})

    def get_fund_facts(self, ticker: str) -> str:
        return json.dumps((get_instrument_meta(ticker.upper()) or {}).get("fund_facts") or {})

    def search_web(self, query: str) -> str:
        if not self._brave_key:
            raise ValueError(f"web search is not configured ({BRAVE_KEY_ENV} is unset)")
        response = self._session.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": 8},
            headers={"X-Subscription-Token": self._brave_key, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_S,
        )
        response.raise_for_status()
        results = (response.json().get("web") or {}).get("results") or []
        return json.dumps([{k: r.get(k) for k in ("title", "url", "description")} for r in results[:8]])

    def fetch_document(self, url: str) -> str:
        if not _public_url(url):
            raise ValueError("only public http(s) URLs can be fetched")
        response = self._session.get(url, timeout=REQUEST_TIMEOUT_S, headers={"User-Agent": "AllotMint fund upkeep"})
        response.raise_for_status()
        if not _public_url(response.url):
            raise ValueError("the document redirected to a non-public URL")
        content = response.content[:MAX_DOCUMENT_BYTES]
        is_pdf = "pdf" in response.headers.get("Content-Type", "").lower() or content.startswith(b"%PDF")
        text = _pdf_text(content) if is_pdf else _html_text(content)
        self.fetched_urls.add(url)
        return re.sub(r"\s+", " ", text).strip()[:MAX_TEXT_CHARS]


def openai_compat_step(cfg: Config) -> Optional[LlmStep]:
    """An :data:`LlmStep` for the configured OpenAI-compatible chat provider, else ``None``."""
    from backend.chat.providers import OPENAI_COMPAT_DEFAULTS, resolve_chat_provider

    provider = resolve_chat_provider(cfg)
    if provider not in OPENAI_COMPAT_DEFAULTS:
        return None
    base_url, model = OPENAI_COMPAT_DEFAULTS[provider]
    api_key = os.getenv("DEEPSEEK_API_KEY") if provider == "deepseek" else None
    if provider == "deepseek" and not api_key:
        return None
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"{(cfg.chat_base_url or base_url).rstrip('/')}/chat/completions"

    def step(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        body = {"model": cfg.chat_model or model, "messages": messages, "tools": tools}
        response = httpx.post(url, json=body, headers=headers, timeout=180.0)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]

    return step


def _run_tool(toolbox: ReadOnlyToolbox, call: Mapping[str, Any]) -> str:
    function = call.get("function") or {}
    name = str(function.get("name") or "")
    try:
        raw = function.get("arguments")
        arguments = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        return toolbox.call(name, arguments)
    except (ValueError, TypeError, requests.RequestException) as exc:
        logger.info("Fund upkeep tool %s failed: %s", sanitise_log_value(name), sanitise_log_value(exc))
        return f"Tool call failed: {exc}"


def _final_json(content: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", content or "", re.DOTALL)
    if not match:
        raise proposals.ProposalRejected("the agent's answer was not JSON")
    try:
        data = json.loads(match.group(0))
    except ValueError as exc:
        raise proposals.ProposalRejected("the agent's answer was not valid JSON") from exc
    if not isinstance(data, dict):
        raise proposals.ProposalRejected("the agent's answer was not a JSON object")
    return data


def _conversation(llm: LlmStep, toolbox: ReadOnlyToolbox, fund: Mapping[str, Any], max_steps: int) -> str:
    """Run the tool loop for one fund; return the model's final text."""
    name = fund.get("name") or fund["ticker"]
    request = f"Find the ongoing charge of {name} (ticker {fund['ticker']}, ISIN {fund.get('isin')})."
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": request},
    ]
    for _ in range(max_steps):
        reply = llm(messages, TOOL_SPECS)
        calls = reply.get("tool_calls") or []
        messages.append(
            {"role": "assistant", "content": reply.get("content") or "", **({"tool_calls": calls} if calls else {})}
        )
        if not calls:
            return str(reply.get("content") or "")
        for call in calls:
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": _run_tool(toolbox, call)})
    raise proposals.ProposalRejected(f"no answer after {max_steps} steps")


def propose_charge(
    fund: Mapping[str, Any],
    *,
    llm: LlmStep,
    toolbox: ReadOnlyToolbox,
    today: Optional[date] = None,
    max_steps: int = MAX_STEPS,
) -> Dict[str, Any]:
    """``{"status": "proposed", "proposal": ...}`` or ``{"status": "not_found"|"rejected", "reason": ...}``."""
    try:
        answer = _final_json(_conversation(llm, toolbox, fund, max_steps))
        if "not_found" in answer:
            return {"status": "not_found", "reason": str(answer["not_found"])}
        if str(answer.get("source_url") or "") not in toolbox.fetched_urls:
            raise proposals.ProposalRejected("the cited source was not fetched during this run")
        proposal = proposals.validate_charge(
            {**answer, "ticker": fund["ticker"], "isin": fund.get("isin")}, today=today
        )
    except proposals.ProposalRejected as exc:
        return {"status": "rejected", "reason": str(exc)}
    return {"status": "proposed", "proposal": proposal}


def needs_charge(meta: Mapping[str, Any], today: date, max_age_days: int = CHARGE_MAX_AGE_DAYS) -> bool:
    """Missing, implausible, or sourced from a document older than ``max_age_days``.

    A hand-entered value with no recorded source date is left alone: its age
    is unknown, and re-researching every such fund each run would hammer issuers.
    """
    if ongoing_charge_pct(meta) is None:
        return True
    source = meta.get(proposals.CHARGE_SOURCE_KEY)
    raw = source.get("document_date") if isinstance(source, dict) else None
    try:
        return date.fromisoformat(str(raw)) < today - timedelta(days=max_age_days) if raw else False
    except ValueError:
        return False
