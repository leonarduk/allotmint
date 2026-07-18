"""Unit tests for publish_pr script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "dev_tools"))
from publish_pr import (
    check_gh_available,
    create_placeholder_pr_body,
    extract_issue_id,
    find_existing_pr,
    get_repo_info,
)


class TestExtractIssueId:
    def test_extracts_id_from_fix_branch(self):
        assert extract_issue_id("fix/issue-4445-slug") == 4445

    def test_extracts_id_from_feat_branch(self):
        assert extract_issue_id("feat/issue-42-some-feature") == 42

    def test_falls_back_to_any_number_in_branch_name(self):
        assert extract_issue_id("4445-slug") == 4445

    def test_returns_none_when_no_number_present(self):
        assert extract_issue_id("main") is None


class TestGetRepoInfo:
    @mock.patch("publish_pr.subprocess.run")
    def test_parses_https_remote(self, mock_run):
        mock_run.return_value = mock.MagicMock(stdout="https://github.com/leonarduk/allotmint.git\n", returncode=0)

        assert get_repo_info() == ("leonarduk", "allotmint")

    @mock.patch("publish_pr.subprocess.run")
    def test_parses_ssh_remote(self, mock_run):
        mock_run.return_value = mock.MagicMock(stdout="git@github.com:leonarduk/allotmint.git\n", returncode=0)

        assert get_repo_info() == ("leonarduk", "allotmint")

    @mock.patch("publish_pr.subprocess.run")
    def test_raises_when_remote_command_fails(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, ["git"])

        with pytest.raises(ValueError):
            get_repo_info()


class TestCreatePlaceholderPrBody:
    def test_includes_closes_directive(self):
        body = create_placeholder_pr_body(4445, "Fix the thing", "Some issue body")

        assert "Closes #4445" in body

    def test_truncates_issue_body_to_200_chars(self):
        long_body = "x" * 500

        body = create_placeholder_pr_body(4445, "Fix the thing", long_body)

        assert ("x" * 200) in body
        assert ("x" * 201) not in body

    def test_falls_back_to_placeholder_text_when_body_empty(self):
        body = create_placeholder_pr_body(4445, "Fix the thing", "")

        assert "<!-- Explain why this change matters -->" in body


class TestFindExistingPr:
    @mock.patch("publish_pr.subprocess.run")
    def test_returns_url_when_pr_exists(self, mock_run):
        mock_run.return_value = mock.MagicMock(stdout="https://github.com/leonarduk/allotmint/pull/123\n", returncode=0)

        url = find_existing_pr("leonarduk", "allotmint", "fix/issue-4445-slug")

        assert url == "https://github.com/leonarduk/allotmint/pull/123"

    @mock.patch("publish_pr.subprocess.run")
    def test_returns_none_when_no_pr_exists(self, mock_run):
        mock_run.return_value = mock.MagicMock(stdout="\n", returncode=0)

        assert find_existing_pr("leonarduk", "allotmint", "fix/issue-4445-slug") is None

    @mock.patch("publish_pr.subprocess.run")
    def test_returns_none_when_gh_command_fails(self, mock_run):
        mock_run.return_value = mock.MagicMock(stdout="", returncode=1)

        assert find_existing_pr("leonarduk", "allotmint", "fix/issue-4445-slug") is None


class TestCreatePr:
    @mock.patch("publish_pr.find_existing_pr")
    @mock.patch("publish_pr.subprocess.run")
    def test_returns_existing_pr_url_without_creating_new_pr(self, mock_run, mock_find_existing):
        from publish_pr import create_pr

        mock_find_existing.return_value = "https://github.com/leonarduk/allotmint/pull/123"

        url = create_pr("leonarduk", "allotmint", "fix/issue-4445-slug", "main", "title", "body")

        assert url == "https://github.com/leonarduk/allotmint/pull/123"
        mock_run.assert_not_called()

    @mock.patch("publish_pr.find_existing_pr")
    @mock.patch("publish_pr.subprocess.run")
    def test_body_temp_file_is_outside_home_dir_and_cleaned_up(self, mock_run, mock_find_existing):
        """The PR body temp file must live in the system temp dir, not ~, and be removed after."""
        from publish_pr import create_pr

        mock_find_existing.return_value = None
        seen_path = {}

        def fake_run(cmd, **kwargs):
            body_file_arg = Path(cmd[cmd.index("--body-file") + 1])
            seen_path["path"] = body_file_arg
            assert body_file_arg.read_text(encoding="utf-8") == "pr body text"
            return mock.MagicMock(
                returncode=0,
                stdout="https://github.com/leonarduk/allotmint/pull/456\n",
            )

        mock_run.side_effect = fake_run

        url = create_pr("leonarduk", "allotmint", "fix/issue-4445-slug", "main", "title", "pr body text")

        assert url == "https://github.com/leonarduk/allotmint/pull/456"
        assert not seen_path["path"].name.startswith(".pr-body-")
        assert seen_path["path"].parent != Path.home()
        assert not seen_path["path"].exists()


class TestCheckGhAvailable:
    @mock.patch("publish_pr.subprocess.run")
    def test_gh_not_installed(self, mock_run, capsys):
        """Should exit 1 with a not-installed message when gh is missing."""
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(SystemExit) as exc_info:
            check_gh_available()

        assert exc_info.value.code == 1
        assert "not installed" in capsys.readouterr().err

    @mock.patch("publish_pr.subprocess.run")
    def test_gh_not_authenticated(self, mock_run, capsys):
        """Should exit 1 with a not-authenticated message when gh auth status fails."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        with pytest.raises(SystemExit) as exc_info:
            check_gh_available()

        assert exc_info.value.code == 1
        assert "not authenticated" in capsys.readouterr().err

    @mock.patch("publish_pr.subprocess.run")
    def test_gh_available(self, mock_run):
        """Should return without raising when gh is installed and authenticated."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        check_gh_available()
