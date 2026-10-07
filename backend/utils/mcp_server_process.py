"""Find, stop and start the local allotmint-pro MCP server process.

Used by ``backend/routes/mcp_server_admin.py`` (local deployments only). No
extra dependency such as psutil: the port owner is looked up with the OS's own
tools -- PowerShell's ``Get-NetTCPConnection`` / ``Win32_Process`` on Windows,
``lsof`` / ``ps`` elsewhere.

Starting reuses the foreground launchers (``scripts/run-mcp-server.ps1`` on
Windows, ``scripts/bash/run-mcp-server.sh`` elsewhere) rather than rebuilding
their command line here, so the env loading, allotmint-pro lookup, PYTHONPATH
and port check stay in one place per platform. The launcher runs detached,
appending its output to ``logs/mcp-server.log``.

Run as ``python -m backend.utils.mcp_server_process stop [--port N]`` to stop
the server from a shell; the launchers' restart flag uses this.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Only a process whose command line contains this is ever stopped.
MCP_SERVER_MARKER = "allotmint_pro.mcp_server.app:app"

_LOOKUP_TIMEOUT_SECONDS = 30
_IS_WINDOWS = sys.platform == "win32"

# One PowerShell call returns the listening PIDs plus each one's process and
# parent process, so a status check costs a single spawn.
_WINDOWS_INSPECT_SCRIPT = """
$ErrorActionPreference = 'Stop'
$owners = @(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique)
$procs = foreach ($id in $owners) {{
  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id"
  if ($p) {{ $p; Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)" }}
}}
$rows = @($procs | Where-Object {{ $_ }} | ForEach-Object {{
  [pscustomobject]@{{
    pid = [int]$_.ProcessId
    ppid = [int]$_.ParentProcessId
    command_line = [string]$_.CommandLine
    started = $(if ($_.CreationDate) {{ [DateTimeOffset]::new($_.CreationDate).ToUnixTimeSeconds() }} else {{ $null }})
  }}
}})
ConvertTo-Json -InputObject @{{ listeners = @($owners); processes = $rows }} -Depth 3 -Compress
"""


class McpProcessError(RuntimeError):
    """A process lookup, stop or start could not be done."""


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int | None
    command_line: str
    started_at: float | None  # Unix seconds

    @property
    def is_mcp_server(self) -> bool:
        return MCP_SERVER_MARKER in self.command_line


@dataclass(frozen=True)
class PortOwner:
    """A process listening on the port, and its parent if known."""

    process: ProcessInfo
    parent: ProcessInfo | None

    def pids_to_stop(self) -> list[int]:
        """The listener, plus its parent when that is the venv launcher.

        A Windows venv ``python.exe`` is a launcher that spawns the real
        interpreter with the same command line; the parent is only included
        when its command line also names the MCP server, so a shell or
        ``run-backend.ps1`` that started it is never touched.
        """

        pids = [self.process.pid]
        if self.parent is not None and self.parent.is_mcp_server:
            pids.insert(0, self.parent.pid)
        return pids


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=_LOOKUP_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise McpProcessError(f"{Path(args[0]).name} failed: {exc}") from exc


def _windows_owners(port: int) -> list[PortOwner]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise McpProcessError("PowerShell not found; cannot see which process holds the port.")
    script = _WINDOWS_INSPECT_SCRIPT.format(port=port)
    proc = _run([powershell, "-NoProfile", "-NonInteractive", "-Command", script])
    if proc.returncode != 0:
        raise McpProcessError(f"Port lookup failed: {proc.stderr.strip() or proc.stdout.strip()}")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise McpProcessError(f"Port lookup returned unexpected output: {exc}") from exc
    return _owners_from_rows(data.get("listeners"), data.get("processes"))


def _as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _owners_from_rows(listeners: object, rows: object) -> list[PortOwner]:
    processes = {}
    for row in _as_list(rows):
        info = ProcessInfo(
            pid=int(row["pid"]),
            ppid=int(row["ppid"]) if row.get("ppid") is not None else None,
            command_line=row.get("command_line") or "",
            started_at=float(row["started"]) if row.get("started") is not None else None,
        )
        processes[info.pid] = info
    owners = []
    for pid in sorted({int(p) for p in _as_list(listeners)}):
        info = processes.get(pid) or ProcessInfo(pid=pid, ppid=None, command_line="", started_at=None)
        parent = processes.get(info.ppid) if info.ppid is not None else None
        owners.append(PortOwner(process=info, parent=parent))
    return owners


def parse_etime(value: str) -> int:
    """Seconds from ``ps -o etime`` (``[[dd-]hh:]mm:ss``)."""

    days, _, clock = value.strip().rpartition("-")
    seconds = 0
    for part in clock.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds + int(days or 0) * 86400


def _posix_process(pid: int) -> ProcessInfo | None:
    proc = _run(["ps", "-o", "pid=,ppid=,etime=,args=", "-p", str(pid)])
    line = proc.stdout.strip()
    if proc.returncode != 0 or not line:
        return None
    fields = line.split(None, 3)
    return ProcessInfo(
        pid=int(fields[0]),
        ppid=int(fields[1]),
        command_line=fields[3] if len(fields) > 3 else "",
        started_at=time.time() - parse_etime(fields[2]),
    )


def _posix_owners(port: int) -> list[PortOwner]:
    lsof = shutil.which("lsof")
    if not lsof:
        raise McpProcessError("lsof not found; cannot see which process holds the port.")
    # lsof exits 1 when nothing matches, which just means no listener.
    proc = _run([lsof, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    owners = []
    for pid in sorted({int(token) for token in proc.stdout.split() if token.isdigit()}):
        info = _posix_process(pid) or ProcessInfo(pid=pid, ppid=None, command_line="", started_at=None)
        parent = _posix_process(info.ppid) if info.ppid else None
        owners.append(PortOwner(process=info, parent=parent))
    return owners


def find_port_owners(port: int) -> list[PortOwner]:
    """Every process listening on TCP ``port`` (normally zero or one)."""

    return _windows_owners(port) if _IS_WINDOWS else _posix_owners(port)


def port_listening(port: int) -> bool:
    """True if something accepts connections on 127.0.0.1:``port``."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_port_free(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not port_listening(port):
            return True
        time.sleep(0.25)
    return not port_listening(port)


def _signal_all(pids: list[int], sig: int) -> list[str]:
    errors = []
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            continue  # already exited (e.g. the launcher once its child died)
        except OSError as exc:
            errors.append(f"pid {pid}: {exc}")
    return errors


def stop_processes(pids: list[int], port: int, timeout: float = 15.0) -> None:
    """Stop ``pids`` and wait for ``port`` to be released.

    On Windows ``os.kill`` is ``TerminateProcess``; elsewhere SIGTERM is tried
    first and SIGKILL follows if the port is still held after ``timeout``.
    """

    errors = _signal_all(pids, signal.SIGTERM)
    if _wait_for_port_free(port, timeout):
        return
    if hasattr(signal, "SIGKILL"):
        errors += _signal_all(pids, signal.SIGKILL)
        if _wait_for_port_free(port, 5.0):
            return
    detail = f" ({'; '.join(errors)})" if errors else ""
    raise McpProcessError(f"Port {port} is still in use after stopping the MCP server{detail}.")


def stop_mcp_server(port: int) -> list[int]:
    """Stop the MCP server listening on ``port``; return the PIDs stopped.

    Raises :class:`McpProcessError`, stopping nothing, if anything else holds
    the port. An empty list means nothing was listening.
    """

    owners = find_port_owners(port)
    foreign = [owner.process for owner in owners if not owner.process.is_mcp_server]
    if foreign:
        holder = foreign[0]
        command = (holder.command_line or "unknown command")[:200]
        raise McpProcessError(
            f"Port {port} is held by another program (pid {holder.pid}: {command}); "
            "it is not the allotmint-pro MCP server, so it was not stopped."
        )
    pids = [pid for owner in owners for pid in owner.pids_to_stop()]
    if pids:
        stop_processes(pids, port)
    return pids


def launcher_command(repo_root: Path, port: int) -> list[str]:
    """The foreground launcher script for this platform, as an argv."""

    if _IS_WINDOWS:
        script = repo_root / "scripts" / "run-mcp-server.ps1"
        shell = shutil.which("pwsh") or shutil.which("powershell")
        args = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Port", str(port)]
    else:
        script = repo_root / "scripts" / "bash" / "run-mcp-server.sh"
        shell = shutil.which("bash")
        args = [str(script), str(port)]
    if not script.is_file():
        raise McpProcessError(f"Launcher script not found: {script}")
    if not shell:
        raise McpProcessError("No shell found to run the MCP server launcher (pwsh/powershell or bash).")
    return [shell, *args]


def _detach_kwargs() -> dict:
    # A literal sys.platform check (not _IS_WINDOWS) so mypy on Linux skips
    # the Windows-only subprocess constants.
    if sys.platform == "win32":
        # CREATE_NO_WINDOW rather than DETACHED_PROCESS: a detached console
        # process would pop a new console window for its python.exe child.
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        return {"creationflags": flags}
    return {"start_new_session": True}


def start_server(repo_root: Path, port: int, log_path: Path) -> subprocess.Popen:
    """Start the launcher detached, appending its output to ``log_path``."""

    command = launcher_command(repo_root, port)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "ab") as log_file:
            return subprocess.Popen(
                command,
                cwd=repo_root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                **_detach_kwargs(),
            )
    except OSError as exc:
        raise McpProcessError(f"Could not start the MCP server launcher: {exc}") from exc


def read_log_tail(log_path: Path, offset: int = 0, max_lines: int = 40) -> list[str]:
    """The last ``max_lines`` lines written to ``log_path`` after byte ``offset``."""

    try:
        with open(log_path, "rb") as log_file:
            log_file.seek(offset)
            text = log_file.read().decode("utf-8", errors="replace")
    except OSError as exc:
        # Reported as a line rather than raised: the caller's own reason
        # already says what failed, and the log is supporting detail.
        return [f"(could not read {log_path}: {exc})"]
    return [line for line in text.splitlines() if line.strip()][-max_lines:]


def log_size(log_path: Path) -> int:
    try:
        return log_path.stat().st_size
    except OSError:
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.utils.mcp_server_process",
        description="Stop the local allotmint-pro MCP server.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    stop = commands.add_parser("stop", help="Stop the MCP server listening on the port.")
    stop.add_argument(
        "--port",
        type=int,
        default=os.environ.get("MCP_SERVER_PORT") or "8001",
        help="Port the server listens on (default: $MCP_SERVER_PORT, else 8001).",
    )
    args = parser.parse_args(argv)
    try:
        pids = stop_mcp_server(args.port)
    except McpProcessError as exc:
        print(exc, file=sys.stderr)
        return 1
    if pids:
        print(f"Stopped the MCP server on port {args.port} (pid {', '.join(map(str, pids))}).", file=sys.stderr)
    else:
        print(f"No MCP server is listening on port {args.port}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
