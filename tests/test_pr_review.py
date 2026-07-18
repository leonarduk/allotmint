"""Unit tests for pr_review script."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "dev_tools"))
from pr_review import extract_issue_body, fetch_pr_details, fetch_pr_diff, get_repo_info


class TestGetRepoInfo:
    @mock.patch("pr_review.subprocess.run")
    def test_https_url(self, mock_run):
        """Should extract owner and repo from HTTPS URL."""
        mock_result = mock.MagicMock()
        mock_result.stdout = "https://github.com/owner/repo.git\n"
        mock_run.return_value = mock_result

        owner, repo = get_repo_info()
        assert owner == "owner"
        assert repo == "repo"

    @mock.patch("pr_review.subprocess.run")
    def test_ssh_url(self, mock_run):
        """Should extract owner and repo from SSH URL."""
        mock_result = mock.MagicMock()
        mock_result.stdout = "git@github.com:owner/repo.git\n"
        mock_run.return_value = mock_result

        owner, repo = get_repo_info()
        assert owner == "owner"
        assert repo == "repo"

    @mock.patch("pr_review.subprocess.run")
    def test_invalid_remote(self, mock_run):
        """Should raise error for invalid remote URL."""
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        with pytest.raises(ValueError, match="Could not determine GitHub repo"):
            get_repo_info()


class TestFetchPrDetails:
    @mock.patch("pr_review.subprocess.run")
    def test_successful_fetch(self, mock_run):
        """Should fetch and parse PR details."""
        mock_result = mock.MagicMock()
        mock_result.stdout = json.dumps(
            {"title": "Fix bug #123", "body": "Closes #456", "baseRefName": "main"}
        )
        mock_run.return_value = mock_result

        details = fetch_pr_details("owner", "repo", 789)
        assert details["title"] == "Fix bug #123"
        assert details["body"] == "Closes #456"

    @mock.patch("pr_review.subprocess.run")
    def test_fetch_failure(self, mock_run):
        """Should exit on fetch failure."""
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="Command failed")

        with pytest.raises(SystemExit) as exc_info:
            fetch_pr_details("owner", "repo", 789)
        assert exc_info.value.code == 1


class TestFetchPrDiff:
    @mock.patch("pr_review.subprocess.run")
    def test_successful_fetch(self, mock_run):
        """Should fetch PR diff."""
        mock_result = mock.MagicMock()
        mock_result.stdout = "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n"
        mock_run.return_value = mock_result

        diff = fetch_pr_diff("owner", "repo", 789)
        assert "diff --git" in diff

    @mock.patch("pr_review.subprocess.run")
    def test_fetch_failure(self, mock_run):
        """Should exit on fetch failure."""
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="Command failed")

        with pytest.raises(SystemExit) as exc_info:
            fetch_pr_diff("owner", "repo", 789)
        assert exc_info.value.code == 1

    @mock.patch("pr_review.subprocess.run")
    def test_binary_file_entries_are_filtered_out(self, mock_run):
        """Binary file diffs must not reach the model."""
        mock_result = mock.MagicMock()
        mock_result.stdout = (
            "diff --git a/logo.png b/logo.png\n"
            "Binary files a/logo.png and b/logo.png differ\n"
            "diff --git a/file.py b/file.py\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        mock_run.return_value = mock_result

        diff = fetch_pr_diff("owner", "repo", 789)

        assert "logo.png" not in diff
        assert "Binary files" not in diff
        assert "file.py" in diff
        assert "+new" in diff


class TestExtractIssueBody:
    @mock.patch("pr_review.subprocess.run")
    def test_extract_closes_reference(self, mock_run):
        """Should extract issue body from Closes reference."""
        mock_result = mock.MagicMock()
        mock_result.stdout = json.dumps({"body": "## What\nFix the thing\n\n## Why\nBecause it's broken"})
        mock_run.return_value = mock_result

        body = extract_issue_body("Closes #456\n\nThis PR fixes the issue.", "owner", "repo")
        assert "What" in body
        assert "Why" in body

    def test_empty_body(self):
        """Should return default message for empty PR body."""
        body = extract_issue_body("", "owner", "repo")
        assert "No linked issue found" in body

    def test_no_issue_reference(self):
        """Should return PR body when no issue reference found."""
        pr_body = "This is a documentation update."
        body = extract_issue_body(pr_body, "owner", "repo")
        assert body == pr_body

    @mock.patch("pr_review.subprocess.run")
    def test_issue_fetch_failure(self, mock_run):
        """Should return PR body if issue fetch fails."""
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="Not found")

        pr_body = "Closes #456\n\nThis PR fixes the issue."
        body = extract_issue_body(pr_body, "owner", "repo")
        assert body == pr_body
