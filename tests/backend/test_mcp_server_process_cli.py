"""Tests for stop_mcp_server and the ``python -m backend.utils.mcp_server_process`` CLI."""

from __future__ import annotations

import pytest

from backend.utils import mcp_server_process as mcp_process
from backend.utils.mcp_server_process import McpProcessError, PortOwner, ProcessInfo

MCP_COMMAND = f"python.exe -m uvicorn {mcp_process.MCP_SERVER_MARKER} --port 8001"


def _owner(pid: int, command: str, parent: ProcessInfo | None = None) -> PortOwner:
    return PortOwner(process=ProcessInfo(pid=pid, ppid=None, command_line=command, started_at=None), parent=parent)


@pytest.fixture
def stopped(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[int], int]]:
    calls: list[tuple[list[int], int]] = []
    monkeypatch.setattr(mcp_process, "stop_processes", lambda pids, port: calls.append((pids, port)))
    return calls


def test_stops_the_mcp_server_and_its_venv_launcher(monkeypatch, stopped):
    launcher = ProcessInfo(pid=10, ppid=1, command_line=MCP_COMMAND, started_at=None)
    monkeypatch.setattr(mcp_process, "find_port_owners", lambda port: [_owner(11, MCP_COMMAND, launcher)])

    assert mcp_process.stop_mcp_server(8001) == [10, 11]
    assert stopped == [([10, 11], 8001)]


def test_nothing_listening_stops_nothing(monkeypatch, stopped):
    monkeypatch.setattr(mcp_process, "find_port_owners", lambda port: [])

    assert mcp_process.stop_mcp_server(8001) == []
    assert stopped == []


def test_refuses_to_stop_another_program(monkeypatch, stopped):
    monkeypatch.setattr(mcp_process, "find_port_owners", lambda port: [_owner(42, "node vite.js")])

    with pytest.raises(McpProcessError, match="pid 42: node vite.js"):
        mcp_process.stop_mcp_server(8001)
    assert stopped == []


def test_cli_stop_reports_the_pids(monkeypatch, capsys, stopped):
    monkeypatch.setattr(mcp_process, "find_port_owners", lambda port: [_owner(11, MCP_COMMAND)])

    assert mcp_process.main(["stop", "--port", "8123"]) == 0
    assert "Stopped the MCP server on port 8123 (pid 11)" in capsys.readouterr().err


def test_cli_port_defaults_to_mcp_server_port(monkeypatch, capsys, stopped):
    seen: list[int] = []
    monkeypatch.setenv("MCP_SERVER_PORT", "8456")
    monkeypatch.setattr(mcp_process, "find_port_owners", lambda port: seen.append(port) or [])

    assert mcp_process.main(["stop"]) == 0
    assert seen == [8456]
    assert "No MCP server is listening on port 8456" in capsys.readouterr().err


def test_cli_exits_non_zero_when_the_port_is_someone_elses(monkeypatch, capsys, stopped):
    monkeypatch.setattr(mcp_process, "find_port_owners", lambda port: [_owner(42, "node vite.js")])

    assert mcp_process.main(["stop"]) == 1
    assert "not the allotmint-pro MCP server" in capsys.readouterr().err
    assert stopped == []
