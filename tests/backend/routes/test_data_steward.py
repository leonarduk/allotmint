"""Tests for the data steward routes and service (#10471). LLM and MCP server are mocked."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.data_steward.service as service
import backend.routes.data_steward as route
from backend.bootstrap.routers import register_routers
from backend.data_steward.llm import LLMReply, ToolCall
from backend.data_steward.store import save_report

ISSUE = {
    "id": "STALE_SERIES:VWRL:L",
    "type": "STALE_SERIES",
    "severity": "medium",
    "entity": {"ticker": "VWRL", "exchange": "L"},
    "description": "VWRL.L last price is 20 days old.",
    "suggested_fix": "Refetch the series.",
    "preview": {},
    "fixable": True,
}

TOOL_RESULTS: Dict[str, Any] = {
    "get_data_quality_report": {"total_count": 1, "issues": [ISSUE], "check_errors": []},
    "list_owners": [{"owner": "alex"}],
    "get_portfolio": {
        "accounts": [{"account_type": "isa", "holdings": [{"ticker": "VWRL.L", "market_value_gbp": 1000.0}]}]
    },
    "get_data_freshness": {"ticker": "VWRL.L", "last_date": "2026-09-19", "stale": True},
}


class FakeSession:
    def __init__(self) -> None:
        self.called: List[str] = []

    async def list_tools(self) -> Any:
        names = ["get_data_freshness", "create_price_trigger", "get_instrument"]
        return SimpleNamespace(
            tools=[SimpleNamespace(name=n, description=n, input_schema={"type": "object"}) for n in names]
        )

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self.called.append(name)
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(TOOL_RESULTS[name]))], is_error=False)


class FakeLLM:
    instances: List["FakeLLM"] = []

    def __init__(self, client: Any, *, base_url: str, model: str) -> None:
        self.replies = [
            LLMReply(
                content="",
                tool_calls=[ToolCall("c1", "get_data_freshness", {"ticker": "VWRL.L"})],
                input_tokens=40,
                output_tokens=5,
            ),
            LLMReply(
                content=(
                    '{"verdict": "fix_available", "root_cause": "source_outage", '
                    '"summary": "20 days stale.", "confidence": 0.9}'
                ),
                input_tokens=60,
                output_tokens=15,
            ),
        ]
        self.offered: List[List[str]] = []
        FakeLLM.instances.append(self)

    async def complete(self, messages: Any, tools: List[Dict[str, Any]]) -> LLMReply:
        self.offered.append([tool["name"] for tool in tools])
        return self.replies.pop(0)


@pytest.fixture
def steward_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    session = FakeSession()

    @asynccontextmanager
    async def fake_mcp_session(url: str):
        yield session

    FakeLLM.instances = []
    monkeypatch.setenv("DATA_STEWARD_REPORTS_URI", str(tmp_path / "reports"))
    monkeypatch.setattr(service, "mcp_session", fake_mcp_session)
    monkeypatch.setattr(service, "OpenAICompatLLM", FakeLLM)
    cfg = route.config
    monkeypatch.setattr(cfg, "mcp_server_url", "http://localhost:8001/mcp")
    monkeypatch.setattr(cfg, "chat_provider", "ollama")
    monkeypatch.setattr(cfg, "chat_model", "qwen-test")
    monkeypatch.setattr(cfg, "disable_auth", True)
    return SimpleNamespace(session=session, reports=tmp_path / "reports", cfg=cfg)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(route.router)
    app.include_router(route.run_router)
    return TestClient(app)


def test_latest_is_404_before_any_run(steward_env: SimpleNamespace) -> None:
    response = _client().get("/data-steward/latest")
    assert response.status_code == 404


def test_run_writes_report_and_latest_serves_it(steward_env: SimpleNamespace) -> None:
    client = _client()
    response = client.post("/data-steward/run")
    assert response.status_code == 200
    report = response.json()

    assert report["status"] == "ok"
    assert report["provider"] == "ollama" and report["model"] == "qwen-test"
    assert report["totals"] == {"input_tokens": 100, "output_tokens": 20, "tool_calls": 1, "cost_usd": 0.0}
    [item] = report["items"]
    assert item["issue_id"] == ISSUE["id"]
    assert item["verdict"] == "fix_available"
    assert item["root_cause"] == "source_outage"
    assert item["exposure_gbp"] == 1000.0 and item["exposure_pct"] == 100.0
    assert item["confidence"] == 0.9
    assert item["evidence"][0]["tool"] == "get_data_freshness"
    assert item["proposed_fix"]["path"] == "/data-quality/issues/STALE_SERIES%3AVWRL%3AL/fix"

    day = report["started_at"][:10]
    assert json.loads((steward_env.reports / f"{day}.json").read_text()) == report
    assert client.get("/data-steward/latest").json() == report

    # The model was only ever offered allowlisted tools, and only those were called.
    assert FakeLLM.instances[0].offered[0] == ["get_data_freshness", "get_instrument"]
    assert "create_price_trigger" not in steward_env.session.called


def test_run_without_mcp_server_saves_an_error_report(
    steward_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(steward_env.cfg, "mcp_server_url", None)
    report = _client().post("/data-steward/run").json()
    assert report["status"] == "error"
    assert "MCP_SERVER_URL" in report["errors"][0]["error"]
    assert _client().get("/data-steward/latest").json()["run_id"] == report["run_id"]


def test_unreachable_mcp_server_saves_an_error_report(
    steward_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    @asynccontextmanager
    async def broken(url: str):
        raise ConnectionError("refused")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(service, "mcp_session", broken)
    report = _client().post("/data-steward/run").json()
    assert report["status"] == "error"
    assert report["errors"][0] == {"stage": "connect", "error": "ConnectionError: refused"}


def test_run_is_refused_while_one_is_in_progress(steward_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route._run_lock, "locked", lambda: True)
    assert _client().post("/data-steward/run").status_code == 409


@pytest.mark.parametrize(("app_env", "expected_status"), [("local", 200), ("aws", 404)])
def test_run_route_only_registered_for_local(
    app_env: str, expected_status: int, steward_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(steward_env.cfg, "app_env", app_env)
    save_report({"run_id": "earlier", "started_at": "2026-10-01T00:00:00Z"})
    app = FastAPI()
    app.state.limiter = None
    with pytest.warns(RuntimeWarning):  # bare app: chat/signup routers warn about missing rate limits
        register_routers(app, steward_env.cfg)
    client = TestClient(app)
    assert client.post("/data-steward/run").status_code == expected_status
    # The report itself is served on every deployment.
    assert client.get("/data-steward/latest").status_code == 200


def test_lambda_handler_runs_and_summarises(steward_env: SimpleNamespace) -> None:
    from backend.lambda_api import data_steward as handler

    result = handler.lambda_handler({}, None)
    assert result["status"] == "ok"
    assert result["issues_investigated"] == 1
    assert (steward_env.reports / "latest.json").exists()


def test_lambda_handler_reports_unexpected_failure(
    steward_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.lambda_api import data_steward as handler

    async def boom(cfg: Any) -> Dict[str, Any]:
        raise RuntimeError("disk full")

    monkeypatch.setattr(handler, "run_and_save", boom)
    assert handler.lambda_handler({}, None) == {"status": "error", "error": "disk full"}
