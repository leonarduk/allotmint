import sys

import pytest
import yaml
from fastapi.testclient import TestClient

from backend import config_module
from backend.app import create_app
from backend.config import ConfigValidationError, reload_config, validate_config_data
from backend.routes import config as routes_config


@pytest.fixture
def config_path(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("auth:\n  google_auth_enabled: false\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: path)
    reload_config()
    yield path
    monkeypatch.undo()
    reload_config()


def test_mcp_tools_default_to_empty_so_every_tool_is_on(config_path):
    assert config_module.config.mcp_tools == {}
    assert config_module.config.mcp_github_repo is None


def test_mcp_section_is_parsed():
    cfg = validate_config_data({"mcp": {"mcp_tools": {"read_data_file": False}, "mcp_github_repo": " o/r "}})

    assert cfg.mcp_tools == {"read_data_file": False}
    assert cfg.mcp_github_repo == "o/r"


@pytest.mark.parametrize("value", [["read_data_file"], {"read_data_file": "no"}, {"": True}])
def test_invalid_mcp_tools_are_rejected(value):
    with pytest.raises(ConfigValidationError, match="mcp_tools"):
        validate_config_data({"mcp": {"mcp_tools": value}})


def test_put_config_saves_switches_under_the_mcp_section(config_path):
    client = TestClient(create_app())

    resp = client.put("/config", json={"mcp": {"mcp_tools": {"read_data_file": False, "get_portfolio": True}}})

    assert resp.status_code == 200
    assert yaml.safe_load(config_path.read_text())["mcp"]["mcp_tools"] == {
        "read_data_file": False,
        "get_portfolio": True,
    }
    assert config_module.config.mcp_tools == {"read_data_file": False, "get_portfolio": True}


def test_saving_one_switch_keeps_the_other_mcp_settings(config_path):
    config_path.write_text("mcp:\n  mcp_github_repo: octo/tracker\n  mcp_tools:\n    get_account: false\n")
    reload_config()
    client = TestClient(create_app())

    resp = client.put("/config", json={"mcp": {"mcp_tools": {"read_data_file": False}}})

    assert resp.status_code == 200
    stored = yaml.safe_load(config_path.read_text())["mcp"]
    assert stored["mcp_github_repo"] == "octo/tracker"
    assert stored["mcp_tools"] == {"get_account": False, "read_data_file": False}


def test_mcp_github_repo_round_trips_as_a_flat_key_from_the_settings_form(config_path):
    config_path.write_text("mcp:\n  mcp_github_repo: old/repo\n")
    reload_config()
    client = TestClient(create_app())

    assert client.get("/config").json()["mcp_github_repo"] == "old/repo"
    resp = client.put("/config", json={"mcp_github_repo": "new/repo"})

    assert resp.status_code == 200
    assert yaml.safe_load(config_path.read_text())["mcp"]["mcp_github_repo"] == "new/repo"
    assert config_module.config.mcp_github_repo == "new/repo"


def test_put_config_rejects_a_bad_switch_without_writing(config_path):
    before = config_path.read_text()
    client = TestClient(create_app())

    resp = client.put("/config", json={"mcp": {"mcp_tools": {"read_data_file": "off"}}})

    assert resp.status_code == 400
    assert config_path.read_text() == before


def test_get_mcp_tools_merges_server_listing_config_and_local_tools(config_path, monkeypatch):
    config_path.write_text("mcp:\n  mcp_tools:\n    delete_price_trigger: false\n")
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8001/mcp")
    reload_config()

    async def listing(url):
        return [{"name": "get_portfolio", "description": "Portfolio"}]

    monkeypatch.setattr(routes_config, "_list_mcp_server_tools", listing)

    body = TestClient(create_app()).get("/config/mcp-tools").json()

    assert body["mcp_error"] is None
    assert body["tools"] == [
        {"name": "delete_price_trigger", "description": "", "enabled": False},
        {
            "name": "export_file",
            "description": "Save a table as a CSV, Excel or Word download.",
            "enabled": True,
        },
        {
            "name": "get_nav_discount",
            "description": "NAV premium/discount for a closed-end fund.",
            "enabled": True,
        },
        {"name": "get_portfolio", "description": "Portfolio", "enabled": True},
        {
            "name": "navigate_to_page",
            "description": "Open a page of the app for the user.",
            "enabled": True,
        },
    ]


def test_get_mcp_tools_reports_an_unreachable_server(config_path, monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8001/mcp")
    reload_config()

    async def listing(url):
        raise ConnectionError("refused by http://internal-host:8001")

    monkeypatch.setattr(routes_config, "_list_mcp_server_tools", listing)

    body = TestClient(create_app()).get("/config/mcp-tools").json()

    assert "Could not list the MCP server's tools" in body["mcp_error"]
    assert "internal-host" not in body["mcp_error"]
    assert [tool["name"] for tool in body["tools"]] == ["export_file", "get_nav_discount", "navigate_to_page"]


def test_get_mcp_tools_without_a_server_url(config_path, monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    reload_config()

    body = TestClient(create_app()).get("/config/mcp-tools").json()

    assert "MCP_SERVER_URL" in body["mcp_error"]
