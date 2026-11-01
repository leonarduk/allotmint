"""Offline smoke tests: pre-deploy-check fails, not skips, on a failed lookup (#11149).

The IAM simulation section of scripts/bash/pre-deploy-check.sh (and its
PowerShell twin) looks up the data bucket with the shared CloudFormation
helper. A failed ``list-stack-resources`` call says nothing about whether the
stack is deployed, so the section must report FAIL rather than the SKIP used
for a stack that is not deployed (#11095).

``PRE_DEPLOY_CHECK_SECTIONS=3`` runs only that section, so no venv, CDK, npm
or nested pytest run is needed. A fake ``aws`` on PATH (from
test_cfn_resource_id) stands in for the CLI: no credentials or network.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.scripts.test_cfn_resource_id import MISSING_STACK, _fake_aws_env, needs_bash, needs_pwsh
from tests.scripts.test_local_dev_ps1 import PWSH

REPO_ROOT = Path(__file__).resolve().parents[2]
BASH_SCRIPT = REPO_ROOT / "scripts" / "bash" / "pre-deploy-check.sh"
PS_SCRIPT = REPO_ROOT / "scripts" / "powershell" / "pre-deploy-check.ps1"
THROTTLED = "An error occurred (Throttling) when calling the ListStackResources operation: Rate exceeded\n"
LOOKUP_FAILED = "FAIL: IAM simulation (could not list BackendLambdaStack resources; see the error above)"
NOT_DEPLOYED = "SKIP: IAM simulation (BackendLambdaStack not deployed or PortfolioDataBucket not found)"


def _env(tmp_path: Path, stderr: str, exit_code: int) -> dict[str, str]:
    return {
        **_fake_aws_env(tmp_path, stdout="", stderr=stderr, exit_code=exit_code),
        "PRE_DEPLOY_CHECK_SECTIONS": "3",
        # Dummy values: only their presence gates the section; the fake aws ignores them.
        "AWS_ACCESS_KEY_ID": "AKIAEXAMPLEEXAMPLE",
        "GITHUB_DEPLOY_ROLE_ARN": "arn:aws:iam::123456789012:role/example-deploy-role",
        "GITHUB_ACTIONS": "",
    }


def _run_bash(tmp_path: Path, stderr: str, exit_code: int) -> tuple[int, str]:
    result = subprocess.run(
        ["bash", str(BASH_SCRIPT)],
        capture_output=True,
        text=True,
        env=_env(tmp_path, stderr, exit_code),
        check=False,
        timeout=60,
    )
    return result.returncode, result.stdout + result.stderr


def _run_pwsh(tmp_path: Path, stderr: str, exit_code: int) -> tuple[int, str]:
    # Report the script's exit code on the last line instead of failing the call.
    script = f"& '{PS_SCRIPT}'; Write-Output \"EXIT=$LASTEXITCODE\""
    result = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        env=_env(tmp_path, stderr, exit_code),
        check=False,
        timeout=60,
    )
    output = result.stdout + result.stderr
    match = re.search(r"^EXIT=(\d+)\s*$", result.stdout, re.MULTILINE)
    assert match, output
    return int(match.group(1)), output


RUNNERS = [
    pytest.param(_run_bash, marks=needs_bash, id="bash"),
    pytest.param(_run_pwsh, marks=needs_pwsh, id="pwsh"),
]


@pytest.mark.parametrize("run", RUNNERS)
def test_failed_lookup_reports_fail_not_skip(tmp_path, run):
    exit_code, output = run(tmp_path, THROTTLED, 255)

    assert exit_code == 1, output
    assert LOOKUP_FAILED in output
    assert "Rate exceeded" in output, "the CLI error must be shown above the FAIL line"
    assert not re.search(r"^SKIP:", output, re.MULTILINE)
    assert "PASS: 0  FAIL: 1  SKIP: 0" in output


@pytest.mark.parametrize("run", RUNNERS)
def test_missing_stack_reports_skip(tmp_path, run):
    # The contrast case: a stack that does not exist is the only lookup error that skips.
    exit_code, output = run(tmp_path, MISSING_STACK, 254)

    assert exit_code == 0, output
    assert NOT_DEPLOYED in output
    assert not re.search(r"^FAIL:", output, re.MULTILINE)
    assert "PASS: 0  FAIL: 0  SKIP: 1" in output


@needs_bash
def test_sections_filter_runs_only_the_listed_section(tmp_path):
    _, output = _run_bash(tmp_path, MISSING_STACK, 254)

    assert re.findall(r"^=== (\d)\.", output, re.MULTILINE) == ["3"]
