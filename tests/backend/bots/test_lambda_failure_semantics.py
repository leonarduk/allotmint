"""Wrapping the scheduled jobs in the bot runner keeps their failure behaviour (#10477).

An exception the job doesn't handle itself must still fail the Lambda
invocation (so EventBridge sees the failure) -- after it has been recorded.
The dividend handler is the exception: it has always caught and returned an
error summary.
"""

from __future__ import annotations

import importlib

import pytest

from backend.bots import runs


def _boom(*_args, **_kwargs):
    raise RuntimeError("boom")


@pytest.mark.parametrize(
    "module,bot_id,target",
    [
        ("backend.lambda_api.price_refresh", "price-refresh", "backend.lambda_api.price_refresh._run_refresh"),
        ("backend.lambda_api.pension_report", "pension-report", "backend.lambda_api.pension_report._run_report"),
        ("backend.lambda_api.trading_agent", "trading-agent", "backend.agent.trading_agent.run"),
    ],
)
def test_unhandled_job_errors_still_fail_the_invocation(monkeypatch, module, bot_id, target):
    handler = importlib.import_module(module)
    monkeypatch.setattr(target, _boom)

    with pytest.raises(RuntimeError, match="boom"):
        handler.lambda_handler({"source": "aws.events"}, None)

    assert runs.latest_run(bot_id).status == "failed"


def test_dividend_handler_still_returns_an_error_summary(monkeypatch):
    handler = importlib.import_module("backend.lambda_api.dividend_refresh")
    monkeypatch.setattr("backend.common.dividends.refresh_dividends", _boom)

    result = handler.lambda_handler({"source": "aws.events"}, None)

    assert result == {"error": "boom", "dividends_created": 0}
    assert runs.latest_run("dividend-refresh").status == "failed"
