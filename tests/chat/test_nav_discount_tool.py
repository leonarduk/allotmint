"""The get_nav_discount local chat tool and its /instrument/nav-discount route. No network."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat import nav_discount_tool
from backend.chat.local_tools import NAVIGATE_TOOL_NAME, ChatPage, LocalTools
from backend.common import nav
from backend.common.nav import NavDiscount
from backend.routes import instrument


def _fake_discount(ticker: str) -> NavDiscount:
    return NavDiscount(ticker=ticker.upper(), applicable=True, nav_gbp=3.805, premium_discount_pct=-9.99)


def test_data_tools_are_opt_in():
    assert LocalTools().tools() == []
    assert not LocalTools().handles(nav_discount_tool.TOOL_NAME)

    local = LocalTools(pages=[ChatPage("/market", "Market")], data_tools=True)
    assert [tool.name for tool in local.tools()] == [NAVIGATE_TOOL_NAME, nav_discount_tool.TOOL_NAME]
    assert local.handles(nav_discount_tool.TOOL_NAME)
    assert local.handles(NAVIGATE_TOOL_NAME)


def test_data_tools_do_not_need_pages():
    local = LocalTools(data_tools=True)
    assert [tool.name for tool in local.tools()] == [nav_discount_tool.TOOL_NAME]
    assert not local.handles(NAVIGATE_TOOL_NAME)


def test_tool_returns_the_nav_discount_as_json(monkeypatch):
    monkeypatch.setattr(nav, "nav_discount", _fake_discount)
    text, is_error = LocalTools(data_tools=True).call(nav_discount_tool.TOOL_NAME, {"ticker": "3in.l"})
    assert not is_error
    payload = json.loads(text)
    assert payload["ticker"] == "3IN.L"
    assert payload["premium_discount_pct"] == -9.99


def test_tool_rejects_a_missing_ticker():
    text, is_error = nav_discount_tool.call({"ticker": "  "})
    assert is_error
    assert "ticker" in text


def test_tool_reports_a_failed_lookup(monkeypatch):
    def broken(ticker):
        raise ValueError("bad csv")

    monkeypatch.setattr(nav, "nav_discount", broken)
    text, is_error = nav_discount_tool.call({"ticker": "3IN.L"})
    assert is_error
    assert "bad csv" in text


def test_tool_is_not_handled_when_data_tools_are_off():
    text, is_error = LocalTools().call(nav_discount_tool.TOOL_NAME, {"ticker": "3IN.L"})
    assert is_error
    assert "Unknown local tool" in text


def test_nav_discount_route(monkeypatch):
    monkeypatch.setattr(nav, "nav_discount", _fake_discount)
    app = FastAPI()
    app.include_router(instrument.router)
    client = TestClient(app)

    response = client.get("/instrument/nav-discount", params={"ticker": "3IN.L"})
    assert response.status_code == 200
    assert response.json()["nav_gbp"] == 3.805

    assert client.get("/instrument/nav-discount", params={"ticker": ".L"}).status_code == 400
