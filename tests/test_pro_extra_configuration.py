"""Regression checks for the private pro extra's credential contract."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pro_extra_uses_explicit_ssh_authentication() -> None:
    """Do not regress to HTTPS that silently depends on ambient credentials."""
    with (ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert pyproject["project"]["optional-dependencies"]["pro"] == [
        "allotmint-pro @ git+ssh://git@github.com/leonarduk/allotmint-pro.git"
    ]


def test_pro_extra_installation_is_documented() -> None:
    """Keep the access preflight and actionable failures near onboarding."""
    runbook = (ROOT / "docs" / "CONTRIBUTOR_RUNBOOK.md").read_text(encoding="utf-8")

    assert "### Installing the private pro extra" in runbook
    assert "ssh -T git@github.com" in runbook
    assert "git ls-remote git@github.com:leonarduk/allotmint-pro.git HEAD" in runbook
    assert 'python -m pip install -e ".[pro]"' in runbook
