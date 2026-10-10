"""/screener/credit-risk: the allotmint-pro credit/distress verdict for one instrument (#10606).

Uses a stand-in for ``get_credit_risk`` so it runs with or without the private
package installed.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError

from backend.app import core_feature_unavailable_handler
from backend.common.core_optional import CoreFeatureUnavailableError
from backend.routes import screener

ROW = {"ticker": "BP.L", "band": "high", "reasons": ["Altman Z 1.35 is below the 1.8 distress line"]}
CONTEXT = {"available": True, "units": "percent", "series": {}}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(screener.router)
    app.add_exception_handler(CoreFeatureUnavailableError, core_feature_unavailable_handler)
    return TestClient(app)


def test_credit_risk_returns_402_without_the_pro_module(monkeypatch):
    monkeypatch.setattr(screener, "get_credit_risk", None)

    resp = _client().get("/screener/credit-risk", params={"ticker": "BP.L"})

    assert resp.status_code == 402
    assert "Credit risk" in resp.json()["detail"]


def test_credit_risk_returns_the_single_row_with_context(monkeypatch):
    seen = []

    def fake(ticker=None):
        seen.append(ticker)
        return {"results": [ROW], "failed": [], "market_context": CONTEXT, "thresholds": {"x": 1}, "note": "n"}

    monkeypatch.setattr(screener, "get_credit_risk", fake)

    resp = _client().get("/screener/credit-risk", params={"ticker": " bp.l "})

    assert resp.status_code == 200
    assert seen == ["BP.L"]
    assert resp.json() == {"result": ROW, "market_context": CONTEXT, "thresholds": {"x": 1}, "note": "n"}


def test_credit_risk_rejects_a_blank_ticker(monkeypatch):
    monkeypatch.setattr(screener, "get_credit_risk", lambda ticker=None: {})

    assert _client().get("/screener/credit-risk", params={"ticker": " "}).status_code == 400


def test_credit_risk_maps_tool_errors_to_400(monkeypatch):
    def boom(ticker=None):
        raise ToolError("get_credit_risk failed: bad ticker")

    monkeypatch.setattr(screener, "get_credit_risk", boom)

    resp = _client().get("/screener/credit-risk", params={"ticker": "X.L"})

    assert resp.status_code == 400
    assert "bad ticker" in resp.json()["detail"]


def test_credit_risk_provider_failure_is_502(monkeypatch):
    def failed(ticker=None):
        return {"results": [], "failed": [{"ticker": ticker, "error": "provider request failed (HTTP 429)"}]}

    monkeypatch.setattr(screener, "get_credit_risk", failed)

    resp = _client().get("/screener/credit-risk", params={"ticker": "X.L"})

    assert resp.status_code == 502
    assert resp.json()["detail"] == "provider request failed (HTTP 429)"
