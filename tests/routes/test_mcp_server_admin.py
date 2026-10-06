"""Tests for the local-only MCP server status/restart route (#9654).

Every process operation (port lookup, stop, launcher spawn, tools/list) is
mocked: these tests must never stop or start a real MCP server.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.mcp_server_admin as admin
from backend.bootstrap.routers import register_routers
from backend.utils import mcp_server_process as mcp_process
from backend.utils.mcp_server_process import PortOwner, ProcessInfo

MCP_COMMAND = "python.exe -m uvicorn allotmint_pro.mcp_server.app:app --host 127.0.0.1 --port 8001"
STARTED = time.time() - 3600


def _proc(pid: int, ppid: int | None = None, command: str = MCP_COMMAND) -> ProcessInfo:
    return ProcessInfo(pid=pid, ppid=ppid, command_line=command, started_at=STARTED)


def _mcp_pair(child: int = 200, parent: int = 100) -> PortOwner:
    """The Windows venv launcher (parent) and the child listening on the port."""

    return PortOwner(process=_proc(child, parent), parent=_proc(parent, 50))


class FakeLauncher:
    def __init__(self, exit_code: int | None = None) -> None:
        self.pid = 999
        self._exit_code = exit_code

    def poll(self) -> int | None:
        return self._exit_code


class Calls:
    def __init__(self) -> None:
        self.stopped: list[tuple[list[int], int]] = []
        self.started: list[int] = []


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "allotmint"
    (repo / "backend").mkdir(parents=True)
    pro = tmp_path / "allotmint-pro"
    (pro / "allotmint_pro" / "mcp_server").mkdir(parents=True)
    monkeypatch.setattr(admin.config, "repo_root", repo)
    monkeypatch.setattr(admin.config, "disable_auth", True)
    monkeypatch.setattr(admin.config, "mcp_server_url", "http://localhost:8001/mcp")
    monkeypatch.delenv("ALLOTMINT_PRO_DIR", raising=False)
    return repo


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """Mock stop/start/port checks; owners and launcher are set per test."""

    record = Calls()
    monkeypatch.setattr(mcp_process, "stop_processes", lambda pids, port: record.stopped.append((pids, port)))
    monkeypatch.setattr(mcp_process, "port_listening", lambda port: True)

    async def fake_tool_count(url: str) -> int:
        return 34

    monkeypatch.setattr(admin, "_tool_count", fake_tool_count)
    monkeypatch.setattr(admin, "_git_head", lambda root: ("a" * 40, STARTED - 60))
    return record


def _set_owners(monkeypatch: pytest.MonkeyPatch, *sequences: list[PortOwner]) -> None:
    """``find_port_owners`` returns each list in turn, then repeats the last."""

    remaining = list(sequences)

    def fake(port: int) -> list[PortOwner]:
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    monkeypatch.setattr(mcp_process, "find_port_owners", fake)


def _set_launcher(monkeypatch: pytest.MonkeyPatch, calls: Calls, launcher: FakeLauncher, output: str = "") -> None:
    def fake_start(repo_root: Path, port: int, log_path: Path) -> FakeLauncher:
        calls.started.append(port)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(output)
        return launcher

    monkeypatch.setattr(mcp_process, "start_server", fake_start)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router)
    return TestClient(app)


def test_restart_stops_launcher_pair_and_starts_new_server(env, calls, monkeypatch):
    _set_owners(monkeypatch, [_mcp_pair()], [_mcp_pair(child=301, parent=300)])
    _set_launcher(monkeypatch, calls, FakeLauncher())

    body = _client().post("/support/mcp-server/restart").json()

    assert body["restarted"] is True, body
    assert calls.stopped == [([100, 200], 8001)]
    assert calls.started == [8001]
    assert body["stopped_pids"] == [100, 200]
    assert body["pid"] == 301
    assert body["tool_count"] == 34


def test_restart_starts_server_when_none_running(env, calls, monkeypatch):
    _set_owners(monkeypatch, [], [_mcp_pair()])
    _set_launcher(monkeypatch, calls, FakeLauncher())

    body = _client().post("/support/mcp-server/restart").json()

    assert body["restarted"] is True
    assert calls.stopped == []
    assert body["pid"] == 200


def test_restart_refuses_foreign_process_on_port(env, calls, monkeypatch):
    foreign = PortOwner(process=_proc(77, 1, command="node server.js --port 8001"), parent=None)
    _set_owners(monkeypatch, [foreign])
    _set_launcher(monkeypatch, calls, FakeLauncher())

    body = _client().post("/support/mcp-server/restart").json()

    assert body["restarted"] is False
    assert "held by another program (pid 77" in body["reason"]
    assert calls.stopped == []
    assert calls.started == []


def test_parent_that_is_not_the_launcher_is_never_stopped():
    shell_parent = _proc(10, 1, command="pwsh -File scripts/run-backend.ps1")
    owner = PortOwner(process=_proc(20, 10), parent=shell_parent)
    assert owner.pids_to_stop() == [20]


@pytest.mark.parametrize(
    "url", ["http://192.168.1.5:8001/mcp", "https://localhost:8001/mcp", "https://abc.lambda-url.aws/mcp"]
)
def test_restart_refuses_non_local_url(env, calls, monkeypatch, url):
    monkeypatch.setattr(admin.config, "mcp_server_url", url)

    def no_lookup(port: int) -> list[PortOwner]:
        raise AssertionError("must not inspect processes for a non-local URL")

    monkeypatch.setattr(mcp_process, "find_port_owners", no_lookup)

    body = _client().post("/support/mcp-server/restart").json()

    assert body["restarted"] is False
    assert "not a plain-HTTP localhost URL" in body["reason"]
    assert calls.started == []


def test_start_failure_surfaces_new_log_lines(env, calls, monkeypatch):
    log_path = env / "logs" / "mcp-server.log"
    log_path.parent.mkdir()
    log_path.write_text("old run output\n", encoding="utf-8")
    _set_owners(monkeypatch, [_mcp_pair()])
    _set_launcher(
        monkeypatch,
        calls,
        FakeLauncher(exit_code=1),
        output="Traceback (most recent call last):\nImportError: cannot import name 'x'\n",
    )

    body = _client().post("/support/mcp-server/restart").json()

    assert body["restarted"] is False
    assert body["reason"] == "The MCP server launcher exited with code 1."
    assert body["log_lines"] == ["Traceback (most recent call last):", "ImportError: cannot import name 'x'"]


def test_stop_failure_is_reported_not_raised(env, calls, monkeypatch):
    _set_owners(monkeypatch, [_mcp_pair()])
    _set_launcher(monkeypatch, calls, FakeLauncher())

    def stuck(pids: list[int], port: int) -> None:
        raise mcp_process.McpProcessError("Port 8001 is still in use after stopping the MCP server.")

    monkeypatch.setattr(mcp_process, "stop_processes", stuck)

    resp = _client().post("/support/mcp-server/restart")

    assert resp.status_code == 200
    assert resp.json()["restarted"] is False
    assert "still in use" in resp.json()["reason"]
    assert calls.started == []


def test_restart_rejects_concurrent_request(env, calls):
    assert admin._restart_lock.acquire(blocking=False)
    try:
        resp = _client().post("/support/mcp-server/restart")
    finally:
        admin._restart_lock.release()
    assert resp.status_code == 409


def test_status_reports_running_server_and_stale_code(env, calls, monkeypatch):
    _set_owners(monkeypatch, [_mcp_pair()])
    changed = env / "backend" / "routes.py"
    changed.write_text("x = 1\n", encoding="utf-8")
    os.utime(changed, (STARTED + 60, STARTED + 60))

    body = _client().get("/support/mcp-server/status").json()

    assert body["running"] is True
    assert body["can_restart"] is True
    assert body["pid"] == 200
    assert body["parent_pid"] == 100
    assert body["tool_count"] == 34
    assert body["pro_commit"] == "a" * 40
    assert body["code_changed"] is True
    assert body["code_changes"] == ["allotmint: backend/routes.py changed after the server started."]


def test_status_without_allotmint_pro_checkout(env, calls, monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOTMINT_PRO_DIR", str(tmp_path / "missing"))
    body = _client().get("/support/mcp-server/status").json()
    assert body["can_restart"] is False
    assert "allotmint-pro not found" in body["reason"]


def test_requires_owner_when_auth_enabled(env, monkeypatch):
    monkeypatch.setattr(admin.config, "disable_auth", False)
    monkeypatch.setattr(admin.config, "allowed_emails", ["owner@example.com"])
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin.get_active_user] = lambda: "someone@example.com"
    assert TestClient(app).post("/support/mcp-server/restart").status_code == 403


@pytest.mark.parametrize(("app_env", "expected_status"), [("local", 200), ("aws", 404)])
def test_route_only_registered_for_local(app_env, expected_status, env, monkeypatch):
    cfg = admin.config
    monkeypatch.setattr(cfg, "app_env", app_env)
    # A non-local URL short-circuits before any process lookup.
    monkeypatch.setattr(cfg, "mcp_server_url", "https://remote.example.com/mcp")
    app = FastAPI()
    app.state.limiter = None
    with pytest.warns(RuntimeWarning):  # bare app: chat/signup routers warn about missing rate limits
        register_routers(app, cfg)
    assert TestClient(app).get("/support/mcp-server/status").status_code == expected_status


def test_windows_lookup_rows_pair_listener_with_parent():
    owners = mcp_process._owners_from_rows(
        200,
        [
            {"pid": 200, "ppid": 100, "command_line": MCP_COMMAND, "started": 1_700_000_000},
            {"pid": 100, "ppid": 50, "command_line": MCP_COMMAND, "started": 1_699_999_999},
        ],
    )
    assert len(owners) == 1
    assert owners[0].process.started_at == 1_700_000_000
    assert owners[0].pids_to_stop() == [100, 200]


@pytest.mark.parametrize(("value", "seconds"), [("05:03", 303), ("01:00:00", 3600), ("2-00:00:01", 172801)])
def test_parse_etime(value, seconds):
    assert mcp_process.parse_etime(value) == seconds


def test_stop_processes_escalates_to_sigkill_when_port_stays_held(monkeypatch):
    import signal

    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(mcp_process.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    waits = iter([False, True])
    monkeypatch.setattr(mcp_process, "_wait_for_port_free", lambda port, timeout: next(waits))
    monkeypatch.setattr(mcp_process.signal, "SIGKILL", 9, raising=False)

    mcp_process.stop_processes([100, 200], 8001)

    assert sent == [(100, signal.SIGTERM), (200, signal.SIGTERM), (100, 9), (200, 9)]


def test_stop_processes_ignores_already_exited_and_raises_if_port_still_held(monkeypatch):
    def kill(pid: int, sig: int) -> None:
        raise ProcessLookupError(pid)

    monkeypatch.setattr(mcp_process.os, "kill", kill)
    monkeypatch.setattr(mcp_process, "_wait_for_port_free", lambda port, timeout: False)

    with pytest.raises(mcp_process.McpProcessError, match="still in use"):
        mcp_process.stop_processes([100], 8001)


def test_posix_lookup_uses_lsof_and_ps(monkeypatch):
    outputs = {
        "lsof": "200\n",
        "200": "  200   100   01:00:00 python -m uvicorn allotmint_pro.mcp_server.app:app --port 8001\n",
        "100": "  100     1   01:00:01 bash scripts/bash/run-mcp-server.sh 8001\n",
    }

    def fake_run(args: list[str]):
        key = "lsof" if args[0].endswith("lsof") else args[-1]
        return mcp_process.subprocess.CompletedProcess(args, 0, stdout=outputs[key], stderr="")

    monkeypatch.setattr(mcp_process.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mcp_process, "_run", fake_run)

    owners = mcp_process._posix_owners(8001)

    assert [owner.process.pid for owner in owners] == [200]
    assert owners[0].process.is_mcp_server
    assert owners[0].parent is not None and owners[0].parent.pid == 100
    # bash started it; only the server itself is stopped.
    assert owners[0].pids_to_stop() == [200]


def test_launcher_command_requires_script(tmp_path):
    with pytest.raises(mcp_process.McpProcessError, match="Launcher script not found"):
        mcp_process.launcher_command(tmp_path, 8001)


def test_launcher_command_uses_platform_launcher():
    repo_root = Path(__file__).resolve().parents[2]
    command = mcp_process.launcher_command(repo_root, 8123)
    expected = "run-mcp-server.ps1" if mcp_process._IS_WINDOWS else "run-mcp-server.sh"
    assert any(arg.endswith(expected) for arg in command)
    assert command[-1] == "8123"


def test_read_log_tail_reads_from_offset(tmp_path):
    log_path = tmp_path / "mcp-server.log"
    log_path.write_bytes(b"old\n")
    offset = mcp_process.log_size(log_path)
    with open(log_path, "ab") as log_file:
        log_file.write(b"new 1\n\nnew 2\n")
    assert mcp_process.read_log_tail(log_path, offset) == ["new 1", "new 2"]
    assert mcp_process.log_size(tmp_path / "missing.log") == 0
