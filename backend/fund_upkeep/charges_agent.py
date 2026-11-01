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

import asyncio
import ipaddress
import json
import logging
import os
import re
import socket
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
        pass  # a hostname, not an IP literal: check what it resolves to
    # A public-looking name can still resolve to a private address (an
    # intranet name, or DNS pointing inwards), so every address must be global.
    addresses = _resolve_host(host)
    return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)


def _resolve_host(host: str) -> List[str]:
    """IP addresses ``host`` resolves to; empty when it does not resolve."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return []
    return sorted({str(info[4][0]).split("%", 1)[0] for info in infos})


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
            params={"q": query, "count": "8"},
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


def _bedrock_assistant(message: Mapping[str, Any]) -> Dict[str, Any]:
    """An OpenAI-shaped assistant message as a Bedrock Converse assistant message."""
    content: List[Dict[str, Any]] = [{"text": message["content"]}] if message.get("content") else []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        raw = function.get("arguments")
        arguments = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        content.append({"toolUse": {"toolUseId": call.get("id"), "name": function.get("name"), "input": arguments}})
    return {"role": "assistant", "content": content}


def _bedrock_conversation(messages: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split OpenAI-shaped ``messages`` into Bedrock ``(system, messages)``.

    Consecutive ``tool`` results become one user turn of ``toolResult`` blocks,
    so the roles alternate as Converse requires (checked by the chat agent's
    ``_validate_message_alternation``).
    """
    from backend.chat.bedrock_agent import _validate_message_alternation

    system: List[Dict[str, Any]] = []
    converted: List[Dict[str, Any]] = []
    for message in messages:
        role = message["role"]
        if role == "system":
            system.append({"text": message["content"]})
        elif role == "assistant":
            converted.append(_bedrock_assistant(message))
        elif role == "tool":
            tool_result = {"toolUseId": message.get("tool_call_id"), "content": [{"text": message["content"]}]}
            result = {"toolResult": tool_result}
            if converted and converted[-1]["role"] == "user" and "toolResult" in converted[-1]["content"][0]:
                converted[-1]["content"].append(result)
            else:
                converted.append({"role": "user", "content": [result]})
        else:
            converted.append({"role": "user", "content": [{"text": message["content"]}]})
    _validate_message_alternation(converted)
    return system, converted


def _bedrock_tool_config(tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    specs = [
        {
            "toolSpec": {
                "name": tool["function"]["name"],
                "description": tool["function"].get("description") or tool["function"]["name"],
                "inputSchema": {"json": tool["function"]["parameters"]},
            }
        }
        for tool in tools
    ]
    return {"tools": specs}


def _openai_reply(output_message: Mapping[str, Any]) -> Dict[str, Any]:
    """A Bedrock Converse output message as an OpenAI-shaped assistant message."""
    blocks = output_message.get("content") or []
    text = "\n".join(block["text"] for block in blocks if "text" in block)
    uses = [block["toolUse"] for block in blocks if "toolUse" in block]
    calls = [
        {
            "id": use["toolUseId"],
            "type": "function",
            "function": {"name": use["name"], "arguments": json.dumps(use.get("input") or {})},
        }
        for use in uses
    ]
    return {"content": text, **({"tool_calls": calls} if calls else {})}


def bedrock_step(cfg: Config, client: Any = None) -> Optional[LlmStep]:
    """An :data:`LlmStep` over the Bedrock Converse API when the provider is ``bedrock``, else ``None``.

    Reuses the chat agent's Bedrock client and transient-error retry. The
    step is synchronous (the bot runs in a worker thread), so each call runs
    the retrying coroutine on its own event loop.
    """
    from backend.chat import bedrock_agent
    from backend.chat.providers import resolve_chat_provider

    if resolve_chat_provider(cfg) != "bedrock":
        return None
    model_id = cfg.bedrock_model_id

    def step(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        system, converted = _bedrock_conversation(messages)
        kwargs: Dict[str, Any] = {"modelId": model_id, "messages": converted, "toolConfig": _bedrock_tool_config(tools)}
        if system:
            kwargs["system"] = system
        bedrock = client if client is not None else bedrock_agent._bedrock_client()
        response = asyncio.run(bedrock_agent._converse_with_retry(bedrock, **kwargs))
        return _openai_reply(response["output"]["message"])

    return step


def configured_step(cfg: Config) -> Optional[LlmStep]:
    """The :data:`LlmStep` for the configured chat provider, or ``None`` when none is usable."""
    return openai_compat_step(cfg) or bedrock_step(cfg)


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


def final_json(content: str) -> Dict[str, Any]:
    """The JSON object in the model's final text, or :class:`proposals.ProposalRejected`."""
    match = re.search(r"\{.*\}", content or "", re.DOTALL)
    if not match:
        raise proposals.ProposalRejected("not_json")
    try:
        data = json.loads(match.group(0))
    except ValueError as exc:
        raise proposals.ProposalRejected("not_json") from exc
    if not isinstance(data, dict):
        raise proposals.ProposalRejected("not_json")
    return data


def run_tool_loop(llm: LlmStep, toolbox: ReadOnlyToolbox, *, system_prompt: str, request: str, max_steps: int) -> str:
    """Run the read-only tool loop for one request; return the model's final text.

    Only :data:`TOOL_SPECS` (the read-only allowlist) is ever offered.
    """
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
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
    raise proposals.ProposalRejected("no_answer")


Validator = Callable[[Dict[str, Any]], Dict[str, Any]]


def propose(
    llm: LlmStep, toolbox: ReadOnlyToolbox, *, system_prompt: str, request: str, validate: Validator, max_steps: int
) -> Dict[str, Any]:
    """Ask the agent, then hold its answer to the proposal rules.

    The answer must cite a ``source_url`` the toolbox fetched during this run
    and pass ``validate`` (a :mod:`.proposals` validator). Returns
    ``{"status": "proposed", "proposal": ...}`` or
    ``{"status": "not_found"|"rejected", "reason": ...}``; nothing is stored.
    """
    try:
        text = run_tool_loop(llm, toolbox, system_prompt=system_prompt, request=request, max_steps=max_steps)
        answer = final_json(text)
        if "not_found" in answer:
            return {"status": "not_found", "reason": str(answer["not_found"])}
        if str(answer.get("source_url") or "") not in toolbox.fetched_urls:
            raise proposals.ProposalRejected("unfetched_source")
        proposal = validate(answer)
    except proposals.ProposalRejected as exc:
        return {"status": "rejected", "reason": proposals.rejection_reason(exc.code)}
    return {"status": "proposed", "proposal": proposal}


def propose_charge(
    fund: Mapping[str, Any],
    *,
    llm: LlmStep,
    toolbox: ReadOnlyToolbox,
    today: Optional[date] = None,
    max_steps: int = MAX_STEPS,
) -> Dict[str, Any]:
    """``{"status": "proposed", "proposal": ...}`` or ``{"status": "not_found"|"rejected", "reason": ...}``."""
    name = fund.get("name") or fund["ticker"]
    request = f"Find the ongoing charge of {name} (ticker {fund['ticker']}, ISIN {fund.get('isin')})."

    def validate(answer: Dict[str, Any]) -> Dict[str, Any]:
        return proposals.validate_charge({**answer, "ticker": fund["ticker"], "isin": fund.get("isin")}, today=today)

    return propose(llm, toolbox, system_prompt=SYSTEM_PROMPT, request=request, validate=validate, max_steps=max_steps)


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
