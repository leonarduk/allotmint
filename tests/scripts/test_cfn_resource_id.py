"""Offline tests for the CloudFormation lookup helpers (#11093, #11094, #11095).

Covers scripts/bash/lib/cfn_resource_id.sh and its PowerShell twin
scripts/powershell/lib/cfn-resource-id.ps1 (skipped without a launchable pwsh).

A fake ``aws`` on PATH stands in for the CLI, so no credentials or network are
needed. The helper is what deploy-lambda.yml and pre-deploy-check.sh call for
every CloudFormation resource lookup.

Run locally with ``pytest tests/scripts/test_cfn_resource_id.py``; CI collects
it in the backend pytest job.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.scripts.test_local_dev_ps1 import PWSH, _run_powershell

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "bash" / "lib" / "cfn_resource_id.sh"
PS_HELPER = REPO_ROOT / "scripts" / "powershell" / "lib" / "cfn-resource-id.ps1"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-lambda.yml"
QUERY = "StackResourceSummaries[?starts_with(LogicalResourceId,'PortfolioDataBucket')].PhysicalResourceId"
FAKE_AWS = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$FAKE_AWS_ARGS"
printf '%b' "${FAKE_AWS_STDOUT:-}"
printf '%b' "${FAKE_AWS_STDERR:-}" >&2
exit "${FAKE_AWS_EXIT:-0}"
"""

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
# The fake aws is a bash script, which Windows pwsh cannot run as a command.
needs_pwsh = pytest.mark.skipif(
    PWSH is None or sys.platform == "win32", reason="needs pwsh on a POSIX host (fake aws is a bash script)"
)
MISSING_STACK = (
    "An error occurred (ValidationError) when calling the ListStackResources operation: "
    "Stack with id BackendLambdaStack does not exist\n"
)


def _fake_aws_env(tmp_path: Path, stdout: str, stderr: str, exit_code: int) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "aws"
    fake.write_text(FAKE_AWS, encoding="utf-8")
    fake.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_AWS_ARGS": str(tmp_path / "args"),
        "FAKE_AWS_STDOUT": stdout,
        "FAKE_AWS_STDERR": stderr,
        "FAKE_AWS_EXIT": str(exit_code),
    }


def _lookup(tmp_path: Path, stdout: str = "", stderr: str = "", exit_code: int = 0) -> subprocess.CompletedProcess:
    return _run_helper(_fake_aws_env(tmp_path, stdout, stderr, exit_code))


def _run_helper(env: dict[str, str]) -> subprocess.CompletedProcess:
    # Same shell options as the workflow steps, plus inherit_errexit so a
    # failure inside the helper would abort here if it weren't contained.
    script = f'set -euo pipefail; shopt -s inherit_errexit; source "{HELPER}"; cfn_resource_id BackendLambdaStack "$1"'
    return subprocess.run(["bash", "-c", script, "lookup", QUERY], capture_output=True, text=True, env=env, check=False)


@needs_bash
def test_passes_stack_and_query_to_list_stack_resources(tmp_path):
    result = _lookup(tmp_path, stdout="bucket-1\n")

    assert result.returncode == 0, result.stderr
    args = (tmp_path / "args").read_text(encoding="utf-8").splitlines()
    assert args == [
        "cloudformation",
        "list-stack-resources",
        "--stack-name",
        "BackendLambdaStack",
        "--query",
        QUERY,
        "--output",
        "text",
    ]


@needs_bash
def test_two_pages_yield_the_single_real_id(tmp_path):
    # Past 100 resources the CLI applies --query per page (#11091): a page
    # with no match prints "None", the page holding the resource prints its id.
    result = _lookup(tmp_path, stdout="None\nbucket-1\n")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "bucket-1\n"


@needs_bash
def test_tab_joined_values_yield_only_the_first(tmp_path):
    result = _lookup(tmp_path, stdout="bucket-1\tbucket-2\nNone\n")

    assert result.stdout == "bucket-1\n"


@needs_bash
@pytest.mark.parametrize("stdout", ["", "None\n", "None\nNone\n", "\n\t\n"])
def test_no_match_prints_nothing_and_succeeds(tmp_path, stdout):
    result = _lookup(tmp_path, stdout=stdout)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@needs_bash
def test_missing_stack_prints_nothing_and_succeeds(tmp_path):
    result = _lookup(
        tmp_path,
        stderr="An error occurred (ValidationError) when calling the ListStackResources operation: "
        "Stack with id BackendLambdaStack does not exist\n",
        exit_code=254,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@needs_bash
@pytest.mark.parametrize(
    "stderr",
    [
        "An error occurred (Throttling) when calling the ListStackResources operation: Rate exceeded\n",
        "An error occurred (ExpiredToken) when calling the ListStackResources operation: expired\n",
        "Could not connect to the endpoint URL\n",
        # A validation error that isn't a missing stack must not read as "not deployed".
        "An error occurred (ValidationError) when calling the ListStackResources operation: "
        "1 validation error detected: Value at 'stackName' failed to satisfy constraint\n",
    ],
)
def test_other_aws_failures_fail_with_the_cli_error(tmp_path, stderr):
    result = _lookup(tmp_path, stdout="", stderr=stderr, exit_code=255)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "list-stack-resources --stack-name BackendLambdaStack failed (exit 255)" in result.stderr
    assert stderr.strip() in result.stderr


@needs_bash
@pytest.mark.parametrize(
    "fake_mktemp",
    [
        "echo 'mktemp: failed to create file via template' >&2\nexit 1\n",
        # A "successful" mktemp that prints no path must not become 2>"".
        "exit 0\n",
    ],
)
def test_mktemp_failure_fails_with_a_clear_error_before_calling_aws(tmp_path, fake_mktemp):
    env = _fake_aws_env(tmp_path, stdout="bucket-1\n", stderr="", exit_code=0)
    (tmp_path / "bin" / "mktemp").write_text(f"#!/usr/bin/env bash\n{fake_mktemp}", encoding="utf-8")
    (tmp_path / "bin" / "mktemp").chmod(0o755)

    result = _run_helper(env)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "cfn_resource_id: mktemp failed to create a file for aws stderr" in result.stderr
    assert "ambiguous redirect" not in result.stderr
    assert not (tmp_path / "args").exists(), "aws must not be called without a stderr capture file"


def _run_steps_using_helper() -> dict[str, str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return {
        step.get("name", ""): step["run"]
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "cfn_resource_id" in step.get("run", "")
    }


def test_workflow_has_no_inline_lookup_pipelines():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert not re.search(r"aws cloudformation list-stack-resources", text)
    assert "found=1" not in text
    # The lookups go through the helper; how many there are is not the point.
    assert re.search(r"\$\(cfn_resource_id BackendLambdaStack ", text)


def test_every_step_using_the_helper_sources_it_first():
    steps = _run_steps_using_helper()

    assert set(steps) >= {
        "Pre-flight IAM permission check",
        "Warm price snapshot",
        "Check recent BackendLambda CloudWatch errors",
    }
    source_line = 'source "$GITHUB_WORKSPACE/scripts/bash/lib/cfn_resource_id.sh"'
    for name, run in steps.items():
        assert source_line in run, name
        assert run.index(source_line) < run.index("$(cfn_resource_id"), name


def test_preflight_check_fails_rather_than_falling_back_on_lookup_error():
    run = _run_steps_using_helper()["Pre-flight IAM permission check"]

    lookups = re.findall(r'="\$\(cfn_resource_id [^\n]*\)"( \|\| \{\n\s+echo "::error::[^\n]*\n\s+exit 1)?', run)
    assert len(lookups) == 3
    assert all(lookups), "each pre-flight lookup must exit on failure instead of using wildcard resources"


def _ps_lookup(tmp_path: Path, stdout: str = "", stderr: str = "", exit_code: int = 0) -> dict:
    env = _fake_aws_env(tmp_path, stdout, stderr, exit_code)
    # 'Stop' as a strict caller would set it: the helper must still return a result.
    script = (
        "$ErrorActionPreference = 'Stop'; "
        f". '{PS_HELPER}'; "
        f"Get-CfnResourceId 'BackendLambdaStack' \"{QUERY}\" | ConvertTo-Json -Compress"
    )
    return json.loads(_run_powershell(script, env=env).stdout)


@needs_pwsh
def test_ps_two_pages_yield_the_single_real_id(tmp_path):
    assert _ps_lookup(tmp_path, stdout="None\nbucket-1\tbucket-2\n") == {"Ok": True, "Id": "bucket-1", "Error": None}


@needs_pwsh
@pytest.mark.parametrize("stdout", ["", "None\n", "None\nNone\n"])
def test_ps_no_match_is_ok_with_no_id(tmp_path, stdout):
    assert _ps_lookup(tmp_path, stdout=stdout) == {"Ok": True, "Id": None, "Error": None}


@needs_pwsh
def test_ps_missing_stack_is_ok_with_no_id(tmp_path):
    assert _ps_lookup(tmp_path, stderr=MISSING_STACK, exit_code=254) == {"Ok": True, "Id": None, "Error": None}


@needs_pwsh
def test_ps_other_aws_failure_is_not_ok(tmp_path):
    stderr = "An error occurred (Throttling) when calling the ListStackResources operation: Rate exceeded\n"

    result = _ps_lookup(tmp_path, stderr=stderr, exit_code=255)

    assert result["Ok"] is False
    assert result["Id"] is None
    assert "failed (exit 255)" in result["Error"]
    assert "Rate exceeded" in result["Error"]
