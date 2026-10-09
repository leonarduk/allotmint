"""Statement reconciliation endpoints (#10474).

``POST /reconciliation/statement`` is read-only: it reads the uploaded
document in memory (never saving it), extracts it with the configured LLM,
matches it against the stored ledger and returns the differences with
suggested changes. Applying a suggestion is a separate, user-confirmed call
to the existing ``POST /transactions`` or ``PUT /transactions/{id}``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Mapping, Sequence

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from backend.auth import get_active_user
from backend.bots import runner
from backend.chat.providers import resolve_chat_provider
from backend.common import holdings_rebuild
from backend.common.authz import ensure_owner_access
from backend.common.instruments import get_instrument_meta
from backend.common.isin import normalise_isin
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.reconciliation import bot, explain, extract, match
from backend.reconciliation.models import ReconciliationResult
from backend.routes._accounts import resolve_accounts_root
from backend.routes.transactions import (
    _find_transaction_account,
    _validate_component,
    load_all_transactions,
    resolve_writable_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

# Statements are a few hundred KB; refuse anything far bigger before parsing.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.get("/provider")
def reconciliation_provider() -> Dict[str, Any]:
    """Which LLM would read an uploaded statement, so the UI can warn before upload."""
    provider = resolve_chat_provider(config)
    return {"llm_provider": provider, "sent_to_cloud": extract.is_cloud_provider(provider)}


def _ledger_for(store: Any, owner: str, account: str) -> List[Dict[str, Any]]:
    return [
        tx.model_dump(mode="json")
        for tx in load_all_transactions(store)
        if tx.owner.lower() == owner.lower() and tx.account.lower() == account.lower()
    ]


def _trade_cash_flag(store: Any, owner: str, account: str) -> bool:
    try:
        canonical = _find_transaction_account(owner, account, store)
    except HTTPException:
        # No transactions file yet: the ledger is empty, so trade settlements
        # cannot have moved cash either.
        return False
    document = store.read_document(owner, f"{canonical}_transactions.json") or {}
    return document.get(holdings_rebuild.TRADE_CASH_FLAG) is True


def _isin_to_ticker(transactions: Sequence[Mapping[str, Any]]) -> Dict[str, str]:
    """Map ISINs to the tickers the ledger uses, from stored instrument metadata."""
    mapping: Dict[str, str] = {}
    for ticker in sorted({str(tx.get("ticker")) for tx in transactions if tx.get("ticker")}):
        isin = normalise_isin(get_instrument_meta(ticker).get("isin"))
        if isin:
            mapping.setdefault(isin, ticker)
    return mapping


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Statement file is too large")
    if not data:
        raise HTTPException(status_code=400, detail="Statement file is empty")
    return data


async def _extract(data: bytes, filename: str) -> Any:
    try:
        return await extract.extract_statement(data, filename, config)
    except extract.UnsupportedDocument as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except extract.ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Statement extraction failed: %s", sanitise_log_value(type(exc).__name__))
        raise HTTPException(status_code=502, detail="The language model could not read the statement") from exc


async def _maybe_explain(owner: str, account: str, result: ReconciliationResult) -> None:
    try:
        result.explanation = await explain.explain_unmatched(owner, account, result.diffs, config)
    except Exception as exc:
        logger.warning("Statement reconciliation explanation failed: %s", sanitise_log_value(type(exc).__name__))
        result.warnings.append("The unmatched rows could not be explained by the assistant")


async def _reconcile(
    request: Request, owner: str, account: str, file: UploadFile, explain_unmatched: bool
) -> ReconciliationResult:
    data = await _read_upload(file)
    extraction = await _extract(data, file.filename or "")

    store, _ = resolve_writable_store(request)
    ledger = _ledger_for(store, owner, account)
    matched, diffs, warnings = match.reconcile(
        extraction,
        ledger,
        owner=owner,
        account=account,
        isin_to_ticker=_isin_to_ticker(ledger),
        trade_cash=_trade_cash_flag(store, owner, account),
    )
    provider = resolve_chat_provider(config)
    result = ReconciliationResult(
        extracted=extraction,
        matched=matched,
        diffs=diffs,
        warnings=[*extraction.warnings, *warnings],
        llm_provider=provider,
        sent_to_cloud=extract.is_cloud_provider(provider),
    )
    if explain_unmatched:
        await _maybe_explain(owner, account, result)
    return result


def _record_run(owner: str, actor: str | None, payload: Dict[str, Any]) -> None:
    """Record one run on the Bots page; bookkeeping never fails the upload."""
    try:
        runner.execute(bot.BOT_ID, "event", owner=owner, actor=actor, payload=payload)
    except Exception as exc:
        logger.error("Could not record the statement reconciliation run: %s", sanitise_log_value(type(exc).__name__))


@router.post("/statement", response_model=ReconciliationResult)
async def reconcile_statement(
    request: Request,
    owner: str = Form(...),
    account: str = Form(...),
    file: UploadFile = File(...),
    explain_unmatched: bool = Form(default=False),
    identity: str | None = Depends(get_active_user),
) -> ReconciliationResult:
    """Extract a broker statement and report how it differs from the ledger. Never writes the ledger.

    Each upload past the access checks records one ``statement-reconciliation``
    run (counts only) on the Bots page, whether it succeeds or fails.
    """
    owner = _validate_component(owner, "owner")
    account = _validate_component(account, "account")
    ensure_owner_access(identity, owner, resolve_accounts_root(request))
    if not await asyncio.to_thread(bot.reconciliation_enabled):
        raise HTTPException(status_code=403, detail="Statement reconciliation is switched off on the Bots page")

    try:
        result = await _reconcile(request, owner, account, file, explain_unmatched)
    except Exception as exc:
        status_code = exc.status_code if isinstance(exc, HTTPException) else 500
        payload = bot.failed_payload(status_code, exc, resolve_chat_provider(config))
        await asyncio.to_thread(_record_run, owner, identity, payload)
        raise

    await asyncio.to_thread(_record_run, owner, identity, bot.reconciled_payload(result))
    logger.info(
        "Statement reconciliation: %s matched, %s differences, %s warnings",
        sanitise_log_value(len(result.matched)),
        sanitise_log_value(len(result.diffs)),
        sanitise_log_value(len(result.warnings)),
    )
    return result
