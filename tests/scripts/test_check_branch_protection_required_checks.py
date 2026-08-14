"""Unit tests for scripts/check_branch_protection_required_checks.py.

These pin down the *context naming convention*, which is the part that is easy
to get wrong and expensive when wrong: a required context that no check-run
produces leaves every PR pending forever. Issue #5728 was caused by the ruleset
using the `Workflow / Job` form the Actions UI displays rather than the
check-run name GitHub actually matches on.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_branch_protection_required_checks.py"
_spec = importlib.util.spec_from_file_location("check_branch_protection_required_checks", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# The real repository must be self-consistent
# ---------------------------------------------------------------------------


def test_repository_passes_its_own_check() -> None:
    assert _mod.main() == 0


def test_ruleset_matches_expected_required_checks() -> None:
    assert _mod.load_ruleset_contexts() == _mod.EXPECTED_REQUIRED_CHECKS


def test_every_required_context_is_produced_by_an_enabled_workflow() -> None:
    unproducible = _mod.EXPECTED_REQUIRED_CHECKS - _mod.workflow_check_contexts()
    assert not unproducible, (
        f"required contexts {sorted(unproducible)} match no enabled workflow job; "
        f"branch protection would wait for them forever"
    )


# ---------------------------------------------------------------------------
# Context naming convention
# ---------------------------------------------------------------------------


def test_normal_job_contexts_are_bare_names_not_workflow_slash_job() -> None:
    """`test`, not `CI / test`. This is the #5728 regression guard."""
    contexts = _mod.workflow_check_contexts()
    assert "test" in contexts
    assert "CI / test" not in contexts
    assert "Frontend lint, type-check and unit tests" in contexts
    assert "CI / Frontend lint, type-check and unit tests" not in contexts


def test_reusable_workflow_contexts_use_caller_job_id_prefix() -> None:
    """A `uses:` job reports `<caller job id> / <called job name>`."""
    assert "ai-review / DeepSeek AI code review" in _mod.workflow_check_contexts()


def test_only_reusable_workflow_contexts_contain_a_separator() -> None:
    """A ` / ` in a required context is a strong signal of the old wrong form.

    Matched on `" / "` with surrounding spaces, so a bare `/` inside a job name
    (`Validate backend/requirements.txt (dry-run)`) is not a false positive.
    """
    slashed = {c for c in _mod.EXPECTED_REQUIRED_CHECKS if " / " in c}
    assert slashed == {"ai-review / DeepSeek AI code review"}, (
        "a required context containing '/' must be a reusable-workflow job; "
        "otherwise it is almost certainly the 'Workflow / Job' UI label, which "
        "GitHub never reports as a check-run name"
    )


def test_job_id_used_when_job_has_no_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "sample.yml").write_text(
        "name: Sample\njobs:\n  bare-id: {runs-on: ubuntu-latest}\n"
        "  named: {name: Pretty Name, runs-on: ubuntu-latest}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_mod, "WORKFLOWS_DIR", workflows)
    assert _mod.workflow_check_contexts(exclude_files=set()) == {"bare-id", "Pretty Name"}


# ---------------------------------------------------------------------------
# Disabled workflows
# ---------------------------------------------------------------------------


def test_disabled_workflows_produce_no_available_contexts() -> None:
    enabled = _mod.workflow_check_contexts()
    everything = _mod.workflow_check_contexts(exclude_files=set())
    # frontend-tests.yml and dependency-review.yml are disabled in GitHub; the
    # contexts they would produce must not be visible as "available".
    assert "frontend-tests" in everything - enabled
    assert "dependency-review" in everything - enabled


def test_no_required_context_comes_from_a_disabled_workflow() -> None:
    everything = _mod.workflow_check_contexts(exclude_files=set())
    disabled_only = everything - _mod.workflow_check_contexts()
    assert not (_mod.EXPECTED_REQUIRED_CHECKS & disabled_only)


def test_disabled_workflow_files_all_exist() -> None:
    """A stale entry here would silently hide a live context from the check."""
    for name in _mod.DISABLED_WORKFLOW_FILES:
        assert (_mod.WORKFLOWS_DIR / name).exists(), f"{name} is listed as disabled but is gone"


# ---------------------------------------------------------------------------
# Failure detection
# ---------------------------------------------------------------------------


def _write_ruleset(path: Path, contexts: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "name": "Main",
                "rules": [
                    {
                        "type": "required_status_checks",
                        "parameters": {"required_status_checks": [{"context": c} for c in contexts]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_unexpected_context_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ruleset = tmp_path / "ruleset.json"
    _write_ruleset(ruleset, [*_mod.EXPECTED_REQUIRED_CHECKS, "surprise"])
    monkeypatch.setattr(_mod, "RULESET_PATH", ruleset)
    assert _mod.main() == 1


def test_missing_context_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ruleset = tmp_path / "ruleset.json"
    _write_ruleset(ruleset, sorted(_mod.EXPECTED_REQUIRED_CHECKS)[1:])
    monkeypatch.setattr(_mod, "RULESET_PATH", ruleset)
    assert _mod.main() == 1


def test_context_from_disabled_workflow_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Re-adding `dependency-review` must fail with a message naming the cause."""
    ruleset = tmp_path / "ruleset.json"
    contexts = [*_mod.EXPECTED_REQUIRED_CHECKS, "dependency-review"]
    _write_ruleset(ruleset, contexts)
    monkeypatch.setattr(_mod, "RULESET_PATH", ruleset)
    monkeypatch.setattr(_mod, "EXPECTED_REQUIRED_CHECKS", _mod.EXPECTED_REQUIRED_CHECKS | {"dependency-review"})
    assert _mod.main() == 1
    assert "disabled workflows" in capsys.readouterr().err
