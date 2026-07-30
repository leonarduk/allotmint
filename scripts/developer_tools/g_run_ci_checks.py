#!/usr/bin/env python3
"""Run the useful, credential-free parts of AllotMint GitHub Actions locally."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    """A local check and the workflow that it mirrors."""

    name: str
    description: str
    workflow: str
    commands: tuple[str, ...]


CHECKS = (
    Check(
        "backend",
        "Backend integration tests, coverage, type checks, and contract sync",
        ".github/workflows/backend-integration.yml",
        (
            "python scripts/check_contract_version_sync.py",
            "python -m mypy backend --config-file mypy.ini --show-error-codes --pretty --explicit-package-bases",
            "pytest --no-cov tests/backend/common/test_data_provider_parity.py -q",
            "pytest tests --ignore=tests/live --cov=backend --cov-report=xml --cov-report=term --cov-fail-under=80 -q",
        ),
    ),
    Check(
        "frontend",
        "Frontend lint, type checking, unit tests, and dependency audit",
        ".github/workflows/frontend-tests.yml and .github/workflows/ci.yml",
        (
            "npm --prefix frontend run lint",
            "npm --prefix frontend run type-check",
            "npm --prefix frontend test -- --run --coverage",
            "npm --prefix frontend audit --audit-level=high",
        ),
    ),
    Check(
        "infrastructure",
        "CDK tests and GitHub Actions workflow lint",
        ".github/workflows/ci.yml and .github/workflows/cdk-dry-run.yml",
        (
            "pytest cdk/tests/ --no-cov",
            "actionlint",
        ),
    ),
    Check(
        "scripts",
        "Bash and PowerShell developer script tests, plus shellcheck",
        ".github/workflows/ci.yml",
        (
            "npx --yes bats@1.13.0 tests/bash/*.bats",
            'pwsh -NoProfile -Command "Import-Module Pester -RequiredVersion '
            '5.6.1 -Force; Invoke-Pester -Path scripts/tests -CI"',
            "shellcheck .github/scripts/*.sh",
        ),
    ),
    Check(
        "backend-deps",
        "Backend requirements.txt dependency-conflict dry-run",
        ".github/workflows/ci.yml (validate-backend-deps)",
        ("pip install --dry-run -r backend/requirements.txt",),
    ),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    choices = tuple(check.name for check in CHECKS)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--check", action="append", choices=choices, help="check to run; repeatable")
    selection.add_argument("--all", action="store_true", help="run every check")
    selection.add_argument("--list", action="store_true", help="list checks and commands")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running them")
    parser.add_argument("--keep-going", action="store_true", help="continue after a failed command")
    return parser.parse_args(argv)


def print_checks() -> None:
    """Print the available checks and their exact commands."""
    for index, check in enumerate(CHECKS, start=1):
        print(f"{index}. {check.name}: {check.description}")
        print(f"   Mirrors: {check.workflow}")
        for command in check.commands:
            print(f"   $ {command}")


def prompt_for_checks() -> list[Check]:
    """Ask an interactive user which checks to run."""
    print_checks()
    answer = input("Select checks by number (comma-separated), or 'all': ").strip().lower()
    if answer == "all":
        return list(CHECKS)
    try:
        indexes = [int(value.strip()) for value in answer.split(",")]
        if not indexes or any(index < 1 or index > len(CHECKS) for index in indexes):
            raise ValueError
    except ValueError as exc:
        raise SystemExit("Invalid selection; use listed numbers or 'all'.") from exc
    return [CHECKS[index - 1] for index in dict.fromkeys(indexes)]


def select_checks(args: argparse.Namespace) -> list[Check]:
    """Resolve flags or the interactive menu to checks."""
    if args.all:
        return list(CHECKS)
    if args.check:
        selected = set(args.check)
        return [check for check in CHECKS if check.name in selected]
    if not sys.stdin.isatty():
        raise SystemExit("No check selected. Use --check NAME, --all, or --list.")
    return prompt_for_checks()


def run_checks(checks: list[Check], root: Path, dry_run: bool, keep_going: bool) -> int:
    """Run selected commands, returning a process-style status code."""
    failures = 0
    for check in checks:
        print(f"\n== {check.name}: {check.description} ==", flush=True)
        for command in check.commands:
            print(f"$ {command}", flush=True)
            if dry_run:
                continue
            result = subprocess.run(command, cwd=root, shell=True, check=False)
            if result.returncode:
                failures += 1
                print(f"FAILED ({result.returncode}): {command}", file=sys.stderr)
                if not keep_going:
                    return result.returncode
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    """Provide the CLI entry point."""
    args = parse_args(argv)
    if args.list:
        print_checks()
        return 0
    root = Path(__file__).resolve().parents[2]
    return run_checks(select_checks(args), root, args.dry_run, args.keep_going)


if __name__ == "__main__":
    raise SystemExit(main())
