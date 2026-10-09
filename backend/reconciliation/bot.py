"""Statement reconciliation as a bot in the shared registry (#10474, #10477).

Reconciliation is upload-triggered: ``POST /reconciliation/statement`` does
the work itself (so a busy or failing run store can never cost the user their
result) and then records one ``event`` run here with **counts only**.

Statements are personal financial data, so nothing from the document may
reach the run history:

* the payload is a closed model (``extra="forbid"``) of counts, the provider
  name and, on failure, the HTTP status and exception *type*;
* :meth:`StatementReconciliationBot.run` never raises, because the runner
  stores a raising bot's traceback and ``str(exc)``, and an exception message
  could quote statement text.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.bots.registry import (
    BotKind,
    BotRunContext,
    BotScope,
    BotSettings,
    RunResult,
    RunStatus,
    Schedule,
    get_bot,
    register_bot,
)
from backend.logging_setup import sanitise_log_value
from backend.reconciliation.models import DiffKind, ReconciliationResult

logger = logging.getLogger(__name__)

BOT_ID = "statement-reconciliation"


class ReconciledPayload(BaseModel):
    """What a finished reconciliation records: counts and the provider, never values."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["reconciled"] = "reconciled"
    rows: int = Field(ge=0)
    matched: int = Field(ge=0)
    differences: int = Field(ge=0)
    warnings: int = Field(ge=0)
    by_kind: Dict[DiffKind, int] = Field(default_factory=dict)
    llm_provider: str
    sent_to_cloud: bool
    explained: bool = False


class FailedPayload(BaseModel):
    """What a failed reconciliation records: the HTTP status and exception type only."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["failed"] = "failed"
    status_code: int
    error_type: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=100)
    llm_provider: str


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: Union[ReconciledPayload, FailedPayload] = Field(discriminator="outcome")


def reconciled_payload(result: ReconciliationResult) -> Dict[str, Any]:
    """Build the run payload for a finished reconciliation."""

    return ReconciledPayload(
        rows=len(result.extracted.rows),
        matched=len(result.matched),
        differences=len(result.diffs),
        warnings=len(result.warnings),
        by_kind=dict(Counter(diff.kind for diff in result.diffs)),
        llm_provider=result.llm_provider,
        sent_to_cloud=result.sent_to_cloud,
        explained=result.explanation is not None,
    ).model_dump()


def failed_payload(status_code: int, exc: BaseException, llm_provider: str) -> Dict[str, Any]:
    """Build the run payload for a failed reconciliation from the exception's type alone.

    The type of the underlying cause is used when there is one, so an
    ``HTTPException`` wrapping an extraction error records e.g. ``UnsupportedDocument``.
    """

    cause = exc.__cause__ or exc
    return FailedPayload(
        status_code=status_code, error_type=type(cause).__name__, llm_provider=llm_provider
    ).model_dump()


def _summary(payload: ReconciledPayload) -> str:
    return f"{payload.matched} matched, {payload.differences} differences, {payload.warnings} warnings"


def _result(context: BotRunContext) -> RunResult:
    if not context.payload:
        return RunResult(
            status="skipped",
            summary="Runs when a statement is uploaded; there is nothing to run on demand",
            owner=context.owner,
        )
    payload = _Payload.model_validate({"data": context.payload}).data
    if isinstance(payload, FailedPayload):
        return RunResult(
            status="failed",
            summary=f"Statement could not be reconciled (HTTP {payload.status_code})",
            report=payload.model_dump(),
            error=payload.error_type,
            owner=context.owner,
            model=payload.llm_provider,
        )
    # A statement the model read no rows from found nothing: never "ok" (#8805).
    status: RunStatus = "ok" if payload.rows else "partial"
    summary = _summary(payload) if payload.rows else "No rows were read from the statement"
    return RunResult(
        status=status,
        summary=summary,
        report=payload.model_dump(),
        owner=context.owner,
        model=payload.llm_provider,
    )


class StatementReconciliationBot:
    id = BOT_ID
    name = "Statement reconciliation"
    description = (
        "Reads an uploaded broker statement or contract note with the configured AI model and reports how it "
        "differs from the ledger. Runs on upload and never writes to the ledger."
    )
    kind: BotKind = "ai"
    scope: BotScope = "owner"
    settings_model: type[BotSettings] = BotSettings
    default_schedule: Optional[Schedule] = None
    timeout_minutes = 10

    def default_settings(self) -> Dict[str, Any]:
        return {"enabled": True, "cadence": "daily"}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        """Turn the route's counts into a run result. Never raises (see the module docstring)."""

        try:
            return _result(context)
        except ValidationError as exc:
            logger.error(
                "Refusing a statement-reconciliation payload with %s invalid field(s)",
                sanitise_log_value(exc.error_count()),
            )
            return RunResult(
                status="failed", summary="Run payload rejected", error="ValidationError", owner=context.owner
            )
        except Exception as exc:
            logger.error("Statement-reconciliation run failed: %s", sanitise_log_value(type(exc).__name__))
            return RunResult(
                status="failed", summary="Could not record the run", error=type(exc).__name__, owner=context.owner
            )


def reconciliation_enabled() -> bool:
    """Whether the Bots page has statement reconciliation switched on.

    Fails open: a settings store that cannot be read is logged, not allowed
    to switch the feature off.
    """

    from backend.bots.settings import load_settings

    try:
        return load_settings(get_bot(BOT_ID)).enabled
    except Exception as exc:
        logger.error(
            "Could not read statement-reconciliation bot settings; treating it as enabled: %s",
            sanitise_log_value(type(exc).__name__),
        )
        return True


register_bot(StatementReconciliationBot(), replace=True)
