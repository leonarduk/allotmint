"""Read a broker statement into validated rows with one LLM call (#10474).

The text layer is read locally (``pypdf`` for PDFs, plain decoding for CSV
and text exports); the LLM only turns that text into structured JSON. Its
answer is validated against :class:`RawStatement` and then checked for
internal arithmetic, so a row that does not add up is flagged rather than
trusted.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
from typing import Any, List, Optional

import httpx
from pydantic import ValidationError

from backend.chat.providers import OPENAI_COMPAT_DEFAULTS, resolve_chat_provider
from backend.common.isin import normalise_isin
from backend.common.ticker_utils import canonical_ticker
from backend.config import Config
from backend.logging_setup import sanitise_log_value
from backend.reconciliation.models import (
    TRADE_TYPES,
    ClosingHolding,
    RawStatement,
    RawStatementRow,
    StatementExtraction,
    StatementRow,
    minor_to_pounds,
    pounds_to_minor,
)

logger = logging.getLogger(__name__)

# Statements are a few pages; anything far larger is not one and would blow
# the model's context window.
MAX_DOCUMENT_CHARS = 60_000
REQUEST_TIMEOUT_SECONDS = 180.0
LOCAL_PROVIDERS = frozenset({"ollama"})

# Pence of slack allowed when checking a statement's own sums: prices are
# printed rounded, so units x price rarely hits the consideration exactly.
_MIN_TOLERANCE_MINOR = 2
_RELATIVE_TOLERANCE = 0.001

EXTRACTION_PROMPT = """You read UK broker documents (contract notes, quarterly or annual statements,
pension contribution and tax-relief statements) and return their contents as JSON.

Return ONE JSON object and nothing else, with exactly these keys:
{
  "document_type": "contract_note" | "statement" | "contribution_statement" | "other",
  "period_start": "YYYY-MM-DD" or null,
  "period_end": "YYYY-MM-DD" or null,
  "opening_cash": number in pounds or null,
  "closing_cash": number in pounds or null,
  "rows": [
    {
      "date": "YYYY-MM-DD (trade date for trades)",
      "type": "BUY" | "SELL" | "DIVIDEND" | "INTEREST" | "DEPOSIT" | "WITHDRAWAL" | "FEES",
      "description": short text as printed,
      "ticker": exchange code if printed (e.g. "BP.L") or null,
      "isin": ISIN if printed or null,
      "units": number or null,
      "price": number or null,
      "price_unit": "GBP" if the price is in pounds, "GBX" if it is in pence,
      "consideration": units x price in pounds, before charges, or null,
      "fees": dealing commission/charges in pounds or null,
      "stamp_duty": stamp duty / PTM levy in pounds or null,
      "amount": cash moved in pounds (positive) for non-trade rows, or the settled total for trades
    }
  ],
  "closing_holdings": [{"ticker": ... or null, "isin": ... or null, "name": ..., "units": number}]
}

Rules:
- Copy numbers exactly as printed; never compute or guess a value that is not on the document.
- All money values are positive numbers in pounds; the type gives the direction.
- Pension contributions and tax-relief top-ups are DEPOSIT rows; platform/management charges are FEES rows.
- Use null for anything not on the document.

Document text:
"""


class ExtractionError(ValueError):
    """The document could not be read or the model's answer was unusable."""


class UnsupportedDocument(ExtractionError):
    """The upload has no text layer we can read (e.g. a scanned PDF)."""


def is_cloud_provider(provider: str) -> bool:
    """True when document text would leave this machine for ``provider``."""
    return provider not in LOCAL_PROVIDERS


def extract_document_text(data: bytes, filename: str) -> str:
    """Return the text of a PDF, CSV or text upload, or raise :class:`UnsupportedDocument`."""
    if data[:5] == b"%PDF-" or filename.lower().endswith(".pdf"):
        text = _pdf_text(data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnsupportedDocument("Only PDF, CSV and text statements are supported") from exc
    text = text.strip()
    if not text:
        raise UnsupportedDocument(
            "The document has no text layer (it may be a scanned image); scanned statements are not supported"
        )
    if len(text) > MAX_DOCUMENT_CHARS:
        raise UnsupportedDocument("The document is too long to be a single statement")
    return text


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, ValueError) as exc:
        raise UnsupportedDocument("The PDF could not be read") from exc


def parse_model_output(raw: str) -> RawStatement:
    """Validate the model's reply against :class:`RawStatement`.

    Tolerates a Markdown code fence or prose around the object, which local
    models often add despite the instructions.
    """
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        raise ExtractionError("The model did not return a JSON object")
    try:
        payload = json.loads(match.group(0))
    except ValueError as exc:
        raise ExtractionError("The model's answer was not valid JSON") from exc
    try:
        return RawStatement.model_validate(payload)
    except ValidationError as exc:
        # Report where the answer is wrong, never the values: they are the
        # user's financial data.
        fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        raise ExtractionError(f"The model's answer did not match the statement schema at: {', '.join(fields)}") from exc


def _tolerance(expected_minor: int) -> int:
    return max(_MIN_TOLERANCE_MINOR, int(abs(expected_minor) * _RELATIVE_TOLERANCE))


def _close(a: Optional[int], b: Optional[int]) -> bool:
    return a is None or b is None or abs(a - b) <= _tolerance(b)


def _price_gbp(row: RawStatementRow) -> Optional[float]:
    if row.price is None:
        return None
    return row.price / 100 if row.price_unit == "GBX" else row.price


def _trade_flags(row: RawStatementRow, price_gbp: Optional[float], fees_minor: int) -> List[str]:
    flags: List[str] = []
    consideration = pounds_to_minor(row.consideration)
    if row.units is None or (price_gbp is None and consideration is None):
        flags.append("trade is missing units or price")
    if row.units is not None and price_gbp is not None and consideration is not None:
        if not _close(pounds_to_minor(row.units * price_gbp), consideration):
            flags.append("units x price does not equal the consideration")
    amount = pounds_to_minor(row.amount)
    if consideration is not None and amount is not None:
        expected = consideration + fees_minor if row.type == "BUY" else consideration - fees_minor
        if not _close(expected, amount):
            flags.append("consideration and charges do not add up to the settled total")
    return flags


def _normalise_row(index: int, row: RawStatementRow) -> StatementRow:
    price_gbp = _price_gbp(row)
    fees_minor = (pounds_to_minor(row.fees) or 0) + (pounds_to_minor(row.stamp_duty) or 0)
    consideration = pounds_to_minor(row.consideration)
    if consideration is None and row.units is not None and price_gbp is not None:
        consideration = pounds_to_minor(row.units * price_gbp)
    is_trade = row.type in TRADE_TYPES
    flags = _trade_flags(row, price_gbp, fees_minor) if is_trade else []
    amount = pounds_to_minor(row.amount)
    if not is_trade and not amount:
        flags.append("cash row has no amount")
    return StatementRow(
        index=index,
        date=row.date,
        type=row.type,
        description=row.description,
        ticker=canonical_ticker(row.ticker) or None,
        isin=normalise_isin(row.isin),
        units=row.units,
        price_gbp=price_gbp,
        consideration_minor=consideration if is_trade else None,
        fees_minor=fees_minor if is_trade else 0,
        amount_minor=amount,
        flags=flags,
    )


_CASH_DIRECTION = {"DEPOSIT": 1, "DIVIDEND": 1, "INTEREST": 1, "SELL": 1, "WITHDRAWAL": -1, "FEES": -1, "BUY": -1}


def _cash_flow_minor(row: StatementRow) -> Optional[int]:
    settled: Optional[int]
    if row.type in TRADE_TYPES:
        if row.amount_minor is not None:
            settled = row.amount_minor
        elif row.consideration_minor is not None:
            settled = row.consideration_minor + (row.fees_minor if row.type == "BUY" else -row.fees_minor)
        else:
            return None
    else:
        settled = row.amount_minor
    return None if settled is None else settled * _CASH_DIRECTION[row.type]


def _cash_warning(extraction: StatementExtraction) -> Optional[str]:
    """Check opening cash + flows = closing cash when the statement gives both ends."""
    opening, closing = extraction.opening_cash_minor, extraction.closing_cash_minor
    if opening is None or closing is None or not extraction.rows:
        return None
    flows = [_cash_flow_minor(row) for row in extraction.rows]
    if any(flow is None for flow in flows):
        return None
    implied = opening + sum(flows)  # type: ignore[arg-type]
    if abs(implied - closing) <= _MIN_TOLERANCE_MINOR:
        return None
    return (
        f"Statement cash does not add up: opening £{minor_to_pounds(opening):,.2f} plus its rows gives "
        f"£{minor_to_pounds(implied):,.2f}, but it states a closing balance of £{minor_to_pounds(closing):,.2f}"
    )


def normalise_statement(raw: RawStatement) -> StatementExtraction:
    """Convert a validated model answer to pence and flag rows whose sums fail."""
    extraction = StatementExtraction(
        document_type=raw.document_type,
        period_start=raw.period_start,
        period_end=raw.period_end,
        opening_cash_minor=pounds_to_minor(raw.opening_cash),
        closing_cash_minor=pounds_to_minor(raw.closing_cash),
        rows=[_normalise_row(index, row) for index, row in enumerate(raw.rows)],
        closing_holdings=[
            ClosingHolding(
                ticker=canonical_ticker(h.ticker) or None, isin=normalise_isin(h.isin), name=h.name, units=h.units
            )
            for h in raw.closing_holdings
        ],
    )
    for row in extraction.rows:
        extraction.warnings.extend(f"Row {row.index + 1} ({row.date}, {row.type}): {flag}" for flag in row.flags)
    cash_warning = _cash_warning(extraction)
    if cash_warning:
        extraction.warnings.append(cash_warning)
    return extraction


async def _complete_openai_compat(prompt: str, cfg: Config, provider: str) -> str:
    default_base_url, default_model = OPENAI_COMPAT_DEFAULTS[provider]
    headers = {}
    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ExtractionError("CHAT_PROVIDER=deepseek requires DEEPSEEK_API_KEY")
        headers["Authorization"] = f"Bearer {api_key}"
    base_url = (cfg.chat_base_url or default_base_url).rstrip("/")
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            json={
                "model": cfg.chat_model or default_model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"].get("content") or ""


async def _complete_bedrock(prompt: str, cfg: Config) -> str:
    from backend.chat.bedrock_agent import _bedrock_client, _converse_with_retry

    response: Any = await _converse_with_retry(
        _bedrock_client(),
        modelId=cfg.bedrock_model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0},
    )
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(block.get("text", "") for block in blocks)


async def complete_extraction(text: str, cfg: Config) -> str:
    """Send the extraction prompt to the configured provider and return its raw reply."""
    provider = resolve_chat_provider(cfg)
    prompt = EXTRACTION_PROMPT + text
    if provider == "bedrock":
        return await _complete_bedrock(prompt, cfg)
    return await _complete_openai_compat(prompt, cfg, provider)


async def extract_statement(data: bytes, filename: str, cfg: Config) -> StatementExtraction:
    """Read ``data`` and return its validated, pence-normalised contents.

    Only counts are logged: the document and the extracted values are
    personal financial data.
    """
    text = await asyncio.to_thread(extract_document_text, data, filename)
    raw = parse_model_output(await complete_extraction(text, cfg))
    extraction = normalise_statement(raw)
    logger.info(
        "Statement extraction: %s rows, %s closing holdings, %s warnings",
        sanitise_log_value(len(extraction.rows)),
        sanitise_log_value(len(extraction.closing_holdings)),
        sanitise_log_value(len(extraction.warnings)),
    )
    return extraction
