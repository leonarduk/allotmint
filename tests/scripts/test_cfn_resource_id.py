"""Offline tests for scripts/bash/lib/cfn_resource_id.sh (#11093, #11094, #11095).

A fake ``aws`` on PATH stands in for the CLI, so no credentials or network are
needed. The helper is what deploy-lambda.yml and pre-deploy-check.sh call for
every CloudFormation resource lookup.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "bash" / "lib" / "cfn_resource_id.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-lambda.yml"
QUERY = "StackResourceSummaries[?starts_with(LogicalResourceId,'PortfolioDataBucket')].PhysicalResourceId"
FAKE_AWS = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$FAKE_AWS_ARGS"
printf '%b' "${FAKE_AWS_STDOUT:-}"
printf '%b' "${FAKE_AWS_STDERR:-}" >&2
exit "${FAKE_AWS_EXIT:-0}"
"""

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _lookup(tmp_path: Path, stdout: str = "", stderr: str = "", exit_code: int = 0) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "aws"
    fake.write_text(FAKE_AWS, encoding="utf-8")
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_AWS_ARGS": str(tmp_path / "args"),
        "FAKE_AWS_STDOUT": stdout,
        "FAKE_AWS_STDERR": stderr,
        "FAKE_AWS_EXIT": str(exit_code),
    }
    # Same shell options as the workflow steps, plus inherit_errexit so a
    # failure inside the helper would abort here if it weren't contained.
    script = f'set -euo pipefail; shopt -s inherit_errexit; source "{HELPER}"; cfn_resource_id BackendLambdaStack "$1"'
    return subprocess.run(["bash", "-c", script, "lookup", QUERY], capture_output=True, text=True, env=env, check=False)


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


def test_two_pages_yield_the_single_real_id(tmp_path):
    # Past 100 resources the CLI applies --query per page (#11091): a page
    # with no match prints "None", the page holding the resource prints its id.
    result = _lookup(tmp_path, stdout="None\nbucket-1\n")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "bucket-1\n"


def test_tab_joined_values_yield_only_the_first(tmp_path):
    result = _lookup(tmp_path, stdout="bucket-1\tbucket-2\nNone\n")

    assert result.stdout == "bucket-1\n"


@pytest.mark.parametrize("stdout", ["", "None\n", "None\nNone\n", "\n\t\n"])
def test_no_match_prints_nothing_and_succeeds(tmp_path, stdout):
    result = _lookup(tmp_path, stdout=stdout)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_missing_stack_prints_nothing_and_succeeds(tmp_path):
    result = _lookup(
        tmp_path,
        stderr="An error occurred (ValidationError) when calling the ListStackResources operation: "
        "Stack with id BackendLambdaStack does not exist\n",
        exit_code=254,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "stderr",
    [
        "An error occurred (Throttling) when calling the ListStackResources operation: Rate exceeded\n",
        "An error occurred (ExpiredToken) when calling the ListStackResources operation: expired\n",
        "Could not connect to the endpoint URL\n",
    ],
)
def test_other_aws_failures_fail_with_the_cli_error(tmp_path, stderr):
    result = _lookup(tmp_path, stdout="", stderr=stderr, exit_code=255)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "list-stack-resources --stack-name BackendLambdaStack failed (exit 255)" in result.stderr
    assert stderr.strip() in result.stderr


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

    assert "list-stack-resources" not in text
    assert "found=1" not in text
    assert len(re.findall(r"\$\(cfn_resource_id BackendLambdaStack ", text)) == 7


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
