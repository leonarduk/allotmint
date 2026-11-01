"""Offline smoke tests: pre-deploy-check fails, not skips, on a failed lookup (#11149).

The IAM simulation section of scripts/bash/pre-deploy-check.sh (and its
PowerShell twin) looks up the data bucket with the shared CloudFormation
helper. A failed ``list-stack-resources`` call says nothing about whether the
stack is deployed, so the section must report FAIL rather than the SKIP used
for a stack that is not deployed (#11095).

``PRE_DEPLOY_CHECK_SECTIONS=3`` runs only that section, so no venv, CDK, npm
or nested pytest run is needed. A fake ``aws`` on PATH (from
test_cfn_resource_id) stands in for the CLI: no credentials or network.

The unset default (every section runs) is pinned without running the
sections, which need a venv, CDK, npm and pytest: the section helper is lifted
out of each script and called with the variable unset (#11304).
"""

from __future__ import annotations

import os
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


# A section is a numbered ``=== N.`` header behind a ``section_enabled N`` /
# ``Test-SectionEnabled N`` guard. The helper's own definition is lifted out of
# each script so the default can be checked without running any section.
BASH_HELPER = re.compile(r"^section_enabled\(\) \{\n.*?^\}\n", re.MULTILINE | re.DOTALL)
PS_HELPER = re.compile(r"^function Test-SectionEnabled\(.*?^\}\n", re.MULTILINE | re.DOTALL)
# Unlike the runs above, these calls need no fake aws, so Windows pwsh is fine.
needs_any_pwsh = pytest.mark.skipif(PWSH is None, reason="no launchable PowerShell available")


def _sections(path: Path, guard: str) -> list[str]:
    """Section numbers the script guards, after checking each has a matching ``=== N.`` header."""
    text = path.read_text(encoding="utf-8")
    guarded = re.findall(rf"^if \(?{guard} (\d+)\)?", text, re.MULTILINE)
    headers = re.findall(r"=== (\d+)\.", text)
    assert guarded == headers, f"{path.name}: guards {guarded} do not match headers {headers}"
    assert len(guarded) > 1, f"{path.name}: expected several sections, found {guarded}"
    return guarded


def _sections_env(sections: str | None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key != "PRE_DEPLOY_CHECK_SECTIONS"}
    if sections is not None:
        env["PRE_DEPLOY_CHECK_SECTIONS"] = sections
    return env


def _helper(path: Path, pattern: re.Pattern[str]) -> str:
    match = pattern.search(path.read_text(encoding="utf-8"))
    assert match, f"section helper not found in {path.name}"
    return match.group(0)


def _enabled_bash(sections: str | None) -> list[str]:
    numbers = " ".join(_sections(BASH_SCRIPT, "section_enabled"))
    loop = f'for n in {numbers}; do if section_enabled "$n"; then echo "$n"; fi; done'
    result = subprocess.run(
        ["bash", "-c", f"set -uo pipefail\n{_helper(BASH_SCRIPT, BASH_HELPER)}{loop}\n"],
        capture_output=True,
        text=True,
        env=_sections_env(sections),
        check=True,
        timeout=30,
    )
    return result.stdout.split()


def _enabled_pwsh(sections: str | None) -> list[str]:
    numbers = ", ".join(_sections(PS_SCRIPT, "Test-SectionEnabled"))
    loop = f"foreach ($n in @({numbers})) {{ if (Test-SectionEnabled $n) {{ Write-Output $n }} }}"
    result = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", f"{_helper(PS_SCRIPT, PS_HELPER)}{loop}"],
        capture_output=True,
        text=True,
        env=_sections_env(sections),
        check=True,
        timeout=60,
    )
    return result.stdout.split()


SECTION_RUNNERS = [
    pytest.param(_enabled_bash, BASH_SCRIPT, "section_enabled", marks=needs_bash, id="bash"),
    pytest.param(_enabled_pwsh, PS_SCRIPT, "Test-SectionEnabled", marks=needs_any_pwsh, id="pwsh"),
]


@pytest.mark.parametrize("sections", [None, ""], ids=["unset", "empty"])
@pytest.mark.parametrize("enabled,script,guard", SECTION_RUNNERS)
def test_sections_unset_or_empty_runs_every_section(enabled, script, guard, sections):
    assert enabled(sections) == _sections(script, guard)


@pytest.mark.parametrize("enabled,script,guard", SECTION_RUNNERS)
def test_sections_filter_enables_only_the_listed_sections(enabled, script, guard):
    # The contrast case: a helper that enables every section regardless also fails.
    assert enabled("0,3") == ["0", "3"]
