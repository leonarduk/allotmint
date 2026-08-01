#!/usr/bin/env python3
"""Compare live GitHub branch protection against the checked-in ruleset.

`scripts/check_branch_protection_required_checks.py` only reads files in the
repository, so it passes cleanly even when GitHub enforces something entirely
different -- which is exactly what happened in issue #5728: the checked-in
ruleset declared 12 required contexts while the live ruleset declared none, and
the real gate was a *classic* branch protection entry with different context
names.

This script closes that hole. It reads (never writes) the GitHub API and fails
when live settings diverge from `.github/rulesets/default-branch-protection.json`:

1. a ruleset with the checked-in `name` exists, is `active`, and targets the
   same refs;
2. its `pull_request` parameters and rule types match the checked-in ones;
3. its required status check contexts match the checked-in ones exactly;
4. classic branch protection does **not** also require status checks (two live
   mechanisms is the drift's root cause);
5. no required context maps to a disabled workflow, which would block every PR
   on a check-run that never arrives.

Read-only by design: applying a ruleset needs repo admin, which the default
`GITHUB_TOKEN` does not have. Reading rulesets also needs elevated access, so
this runs on a schedule with a PAT rather than on every PR.

Usage:
    python scripts/check_live_branch_protection.py [--repo owner/name]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Importable both as `python scripts/check_live_branch_protection.py` (script
# dir already on sys.path) and via importlib from tests (it is not).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_branch_protection_required_checks import (  # noqa: E402
    DISABLED_WORKFLOW_FILES,
    RULESET_PATH,
    WORKFLOWS_DIR,
    workflow_check_contexts,
)

DEFAULT_REPO = "leonarduk/allotmint"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_UNAVAILABLE = 2

# `pull_request` rule parameters that GitHub returns but that the checked-in
# JSON does not need to declare. Compared only when present in both.
_OPTIONAL_PR_PARAMETERS = frozenset({"required_reviewers", "automatic_copilot_code_review_enabled"})


class ApiUnavailable(RuntimeError):
    """Raised when the GitHub API could not be queried at all."""


Fetch = Callable[[str], Any]


def gh_api(path: str) -> Any:
    """Fetch `path` from the GitHub API via the `gh` CLI.

    Raises ApiUnavailable when `gh` is missing or the token lacks access;
    returns None for a 404 (the resource legitimately does not exist).
    """
    try:
        result = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment dependent
        raise ApiUnavailable("the `gh` CLI is not installed") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "404" in stderr or "Not Found" in stderr:
            return None
        raise ApiUnavailable(f"`gh api {path}` failed: {stderr}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ApiUnavailable(f"`gh api {path}` returned non-JSON output") from exc


def load_checked_in_ruleset() -> dict[str, Any]:
    return json.loads(RULESET_PATH.read_text(encoding="utf-8"))


def rules_by_type(ruleset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    for rule in ruleset.get("rules", []):
        if isinstance(rule, dict) and isinstance(rule.get("type"), str):
            rules[rule["type"]] = rule
    return rules


def required_checks(ruleset: dict[str, Any]) -> dict[str, Any]:
    """Map required context -> integration_id (None if unset)."""
    rule = rules_by_type(ruleset).get("required_status_checks")
    if not rule:
        return {}
    checks = rule.get("parameters", {}).get("required_status_checks", [])
    return {
        c["context"]: c.get("integration_id")
        for c in checks
        if isinstance(c, dict) and isinstance(c.get("context"), str)
    }


def required_contexts(ruleset: dict[str, Any]) -> set[str]:
    return set(required_checks(ruleset))


def find_live_ruleset(fetch: Fetch, repo: str, name: str) -> dict[str, Any]:
    listing = fetch(f"repos/{repo}/rulesets")
    if not isinstance(listing, list):
        raise ApiUnavailable(f"repos/{repo}/rulesets did not return a list")
    matches = [r for r in listing if isinstance(r, dict) and r.get("name") == name]
    if not matches:
        available = sorted(str(r.get("name")) for r in listing if isinstance(r, dict))
        raise LookupError(
            f"no live ruleset named {name!r}; GitHub has: {available or '(none)'}. "
            f"Apply {RULESET_PATH.name} -- see docs/BRANCH_PROTECTION.md."
        )
    detail = fetch(f"repos/{repo}/rulesets/{matches[0]['id']}")
    if not isinstance(detail, dict):
        raise ApiUnavailable(f"could not read ruleset {matches[0]['id']}")
    return detail


def compare_conditions(expected: dict[str, Any], live: dict[str, Any]) -> list[str]:
    expected_ref = expected.get("conditions", {}).get("ref_name", {})
    live_ref = live.get("conditions", {}).get("ref_name", {})
    errors: list[str] = []
    for key in ("include", "exclude"):
        want = sorted(expected_ref.get(key, []) or [])
        got = sorted(live_ref.get(key, []) or [])
        if want != got:
            errors.append(f"ruleset conditions.ref_name.{key}: checked-in {want}, live {got}")
    return errors


def compare_rule_types(expected: dict[str, Any], live: dict[str, Any]) -> list[str]:
    want = set(rules_by_type(expected))
    got = set(rules_by_type(live))
    errors: list[str] = []
    if want - got:
        errors.append(f"ruleset is missing rule types that are checked in: {sorted(want - got)}")
    if got - want:
        errors.append(f"live ruleset has rule types that are not checked in: {sorted(got - want)}")
    return errors


def compare_pull_request_parameters(expected: dict[str, Any], live: dict[str, Any]) -> list[str]:
    want = rules_by_type(expected).get("pull_request", {}).get("parameters", {})
    got = rules_by_type(live).get("pull_request", {}).get("parameters", {})
    errors: list[str] = []
    for key, want_value in sorted(want.items()):
        if key in _OPTIONAL_PR_PARAMETERS or key not in got:
            continue
        got_value = got[key]
        if isinstance(want_value, list) and isinstance(got_value, list):
            if sorted(want_value) != sorted(got_value):
                errors.append(
                    f"pull_request.{key}: checked-in {sorted(want_value)}, live {sorted(got_value)}"
                )
        elif want_value != got_value:
            errors.append(f"pull_request.{key}: checked-in {want_value!r}, live {got_value!r}")
    return errors


def compare_required_checks(expected: dict[str, Any], live: dict[str, Any]) -> list[str]:
    want_checks = required_checks(expected)
    got_checks = required_checks(live)
    want = set(want_checks)
    got = set(got_checks)
    errors: list[str] = []
    if want - got:
        errors.append(f"live ruleset does not require checked-in contexts: {sorted(want - got)}")
    if got - want:
        errors.append(
            f"live ruleset requires contexts that are not checked in: {sorted(got - want)}"
        )

    # A required context can silently switch which GitHub App produces it --
    # e.g. a job migrating from a first-party Action to a third-party App --
    # without the context string itself changing. integration_id catches that.
    for context in sorted(want & got):
        want_id, got_id = want_checks[context], got_checks[context]
        if want_id is not None and got_id is not None and want_id != got_id:
            errors.append(
                f"required check {context!r} integration_id: checked-in {want_id}, live {got_id}"
            )

    want_strict = (
        rules_by_type(expected)
        .get("required_status_checks", {})
        .get("parameters", {})
        .get("strict_required_status_checks_policy")
    )
    got_strict = (
        rules_by_type(live)
        .get("required_status_checks", {})
        .get("parameters", {})
        .get("strict_required_status_checks_policy")
    )
    if want_strict is not None and got_strict is not None and want_strict != got_strict:
        errors.append(
            f"strict_required_status_checks_policy: checked-in {want_strict}, live {got_strict}"
        )
    return errors


def check_classic_protection(fetch: Fetch, repo: str, branch: str) -> list[str]:
    """Classic protection must not also require status checks."""
    protection = fetch(f"repos/{repo}/branches/{branch}/protection")
    if not isinstance(protection, dict):
        return []
    contexts = protection.get("required_status_checks", {}).get("contexts") or []
    if contexts:
        return [
            "classic branch protection also requires status checks "
            f"{sorted(contexts)} on {branch}; two live mechanisms is the drift "
            "this check exists to prevent. Remove the classic required-checks "
            "entry once the ruleset is confirmed working."
        ]
    return []


def disabled_workflow_names(fetch: Fetch, repo: str) -> set[str]:
    """Return the file names of workflows GitHub reports as disabled.

    Restricted to files that still exist in this checkout: GitHub keeps
    listing workflows from deleted branches, and those cannot produce a
    context anyone could require here.
    """
    payload = fetch(f"repos/{repo}/actions/workflows?per_page=100")
    if not isinstance(payload, dict):
        raise ApiUnavailable(f"could not list workflows for {repo}")
    present = {path.name for path in WORKFLOWS_DIR.glob("*.yml")}
    disabled: set[str] = set()
    for workflow in payload.get("workflows", []):
        if not isinstance(workflow, dict):
            continue
        if workflow.get("state") in {"disabled_manually", "disabled_inactivity"}:
            name = Path(str(workflow.get("path", ""))).name
            if name in present:
                disabled.add(name)
    return disabled


def check_contexts_are_producible(fetch: Fetch, repo: str, contexts: set[str]) -> list[str]:
    """Fail when a required context can never be reported.

    Uses GitHub's own view of which workflows are disabled rather than the
    hard-coded `DISABLED_WORKFLOW_FILES` list, so disabling a workflow in the
    UI is caught without a code change.
    """
    disabled_files = disabled_workflow_names(fetch, repo)
    producible = workflow_check_contexts(exclude_files=disabled_files)
    everything = workflow_check_contexts(exclude_files=set())

    errors: list[str] = []
    if stale := sorted(disabled_files - DISABLED_WORKFLOW_FILES):
        errors.append(
            "workflows are disabled in GitHub but not listed in "
            f"DISABLED_WORKFLOW_FILES: {stale}"
        )
    if blocked := sorted(contexts & (everything - producible)):
        errors.append(
            f"required contexts map to disabled workflows and can never report: {blocked}"
        )
    if unknown := sorted(contexts - everything):
        errors.append(f"required contexts match no workflow job in this repo: {unknown}")
    return errors


def run(fetch: Fetch, repo: str) -> tuple[int, list[str]]:
    expected = load_checked_in_ruleset()
    try:
        live = find_live_ruleset(fetch, repo, expected["name"])
    except LookupError as exc:
        return EXIT_DRIFT, [str(exc)]

    errors: list[str] = []
    if live.get("enforcement") != expected.get("enforcement"):
        errors.append(
            f"ruleset enforcement: checked-in {expected.get('enforcement')!r}, "
            f"live {live.get('enforcement')!r}"
        )
    errors += compare_conditions(expected, live)
    errors += compare_rule_types(expected, live)
    errors += compare_pull_request_parameters(expected, live)
    errors += compare_required_checks(expected, live)
    errors += check_classic_protection(fetch, repo, "main")
    errors += check_contexts_are_producible(fetch, repo, required_contexts(expected))

    return (EXIT_DRIFT if errors else EXIT_OK), errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/name (default: %(default)s)")
    args = parser.parse_args(argv)

    try:
        exit_code, errors = run(gh_api, args.repo)
    except ApiUnavailable as exc:
        print(f"Could not query GitHub: {exc}", file=sys.stderr)
        print(
            "Reading rulesets requires admin access; supply a PAT via GH_TOKEN.",
            file=sys.stderr,
        )
        return EXIT_UNAVAILABLE

    for error in errors:
        print(f"Branch protection drift: {error}", file=sys.stderr)
    if exit_code == EXIT_OK:
        print(f"Live branch protection on {args.repo} matches {RULESET_PATH.name}.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
