"""Tests for Get-PortStopPlan in scripts/lib/local-dev.ps1 (run-all.ps1).

The plan decides which processes run-all.ps1 kills, so these pin that an
unrelated listener or shell is never in it. Skipped where no launchable
PowerShell is available.
"""

import json
import os

import pytest

from tests.scripts.test_local_dev_ps1 import LIB, PWSH, _run_powershell

MARKER = r"backend\.local_api\.main:app|run-backend\.ps1|--multiprocessing-fork"

pytestmark = pytest.mark.skipif(PWSH is None, reason="no launchable PowerShell available")

SHELL = {"ProcessId": 1, "ParentProcessId": 0, "CommandLine": "pwsh.exe -NoExit"}
LAUNCHER_SHELL = {"ProcessId": 2, "ParentProcessId": 1, "CommandLine": "pwsh.exe -File run-backend.ps1"}
RELOADER = {"ProcessId": 3, "ParentProcessId": 2, "CommandLine": "python -m uvicorn backend.local_api.main:app"}
WORKER = {"ProcessId": 4, "ParentProcessId": 3, "CommandLine": "python -c spawn_main() --multiprocessing-fork"}
HELPER = {"ProcessId": 5, "ParentProcessId": 4, "CommandLine": "conhost.exe"}
OTHER = {"ProcessId": 6, "ParentProcessId": 1, "CommandLine": "postgres.exe"}
ALL = [SHELL, LAUNCHER_SHELL, RELOADER, WORKER, HELPER, OTHER]


def _plan(listeners: list[int], processes: list[dict]) -> dict:
    script = (
        f". '{LIB}'; "
        "$processes = @($env:TEST_PROCESSES | ConvertFrom-Json) | ForEach-Object { $_ }; "
        f"$plan = Get-PortStopPlan -Listeners @({','.join(map(str, listeners))}) "
        f"-Processes $processes -Marker '{MARKER}'; "
        "@{ pids = @($plan.Pids); foreign = @($plan.Foreign | ForEach-Object { $_.ProcessId }) } "
        "| ConvertTo-Json -Compress"
    )
    env = {**os.environ, "TEST_PROCESSES": json.dumps(processes)}
    return json.loads(_run_powershell(script, env=env).stdout)


def test_listener_stops_with_matching_ancestors_and_descendants_only():
    assert _plan([4], ALL) == {"pids": [2, 3, 4, 5], "foreign": []}


def test_unrelated_listener_is_reported_and_not_stopped():
    assert _plan([6], ALL) == {"pids": [], "foreign": [6]}


def test_no_listener_means_nothing_to_stop():
    assert _plan([], ALL) == {"pids": [], "foreign": []}


def test_dead_listener_is_judged_by_the_child_holding_its_socket():
    without_reloader = [p for p in ALL if p is not RELOADER]
    assert _plan([3], without_reloader) == {"pids": [4, 5], "foreign": []}


def test_dead_listener_with_no_children_is_foreign():
    assert _plan([99], ALL) == {"pids": [], "foreign": [99]}
