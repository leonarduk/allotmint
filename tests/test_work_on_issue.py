"""Unit tests for work_on_issue script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "dev_tools"))
from work_on_issue import main, slugify


class TestSlugify:
    def test_normal_title(self):
        assert slugify("Fix login bug") == "fix-login-bug"

    def test_emoji_only_title_falls_back_to_deterministic_hash(self):
        slug = slugify("\U0001f680\U0001f680\U0001f680")
        assert slug
        assert slug == slugify("\U0001f680\U0001f680\U0001f680")

    def test_fallback_is_short_and_hex(self):
        slug = slugify("\U0001f680")
        assert len(slug) == 8
        int(slug, 16)  # raises ValueError if not hex

    def test_different_empty_titles_produce_different_fallbacks(self):
        assert slugify("\U0001f680") != slugify("\U0001f389")


def _run_main(monkeypatch, tmp_path, cli_args, sleep_mock):
    """Run main() with every external side effect mocked, return the resolved branch name."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["work_on_issue.py", *cli_args])
    monkeypatch.setattr("work_on_issue.time.sleep", sleep_mock)
    monkeypatch.setattr("work_on_issue.get_repo_info", lambda: ("leonarduk", "allotmint"))
    monkeypatch.setattr(
        "work_on_issue.fetch_issue",
        lambda owner, repo, issue_id: {"title": "Some Issue Title", "body": "body text"},
    )
    monkeypatch.setattr("work_on_issue.get_main_branch_sha", lambda owner, repo: "deadbeef")
    monkeypatch.setattr("work_on_issue.create_branch", lambda owner, repo, branch_name, sha, token: None)

    run_calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        run_calls.append(cmd)
        return mock.MagicMock(returncode=0, stdout="")

    monkeypatch.setattr("work_on_issue.subprocess.run", fake_run)

    main()

    checkout_calls = [c for c in run_calls if c[:2] == ["git", "checkout"]]
    assert checkout_calls, f"no git checkout call found in {run_calls}"
    return checkout_calls[0][3]


class TestBranchTypeFlag:
    def test_defaults_to_fix_prefix(self, monkeypatch, tmp_path):
        sleep_mock = mock.MagicMock()
        branch_name = _run_main(monkeypatch, tmp_path, ["4445"], sleep_mock)

        assert branch_name.startswith("fix/issue-4445-")

    def test_feat_flag_uses_feat_prefix(self, monkeypatch, tmp_path):
        sleep_mock = mock.MagicMock()
        branch_name = _run_main(monkeypatch, tmp_path, ["4445", "--type", "feat"], sleep_mock)

        assert branch_name.startswith("feat/issue-4445-")

    def test_rejects_invalid_type(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "argv", ["work_on_issue.py", "4445", "--type", "bogus"])

        with pytest.raises(SystemExit):
            main()


class TestFetchDelay:
    def test_sleeps_before_fetching_new_branch(self, monkeypatch, tmp_path):
        sleep_mock = mock.MagicMock()
        _run_main(monkeypatch, tmp_path, ["4445"], sleep_mock)

        sleep_mock.assert_called_once()
