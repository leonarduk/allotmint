"""Unit tests for local_review script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "dev_tools"))
from local_review import (
    generate_markdown_report,
    get_current_branch,
    get_git_root,
    get_local_diff,
    save_report,
)


class TestGetGitRoot:
    @mock.patch("local_review.subprocess.run")
    def test_successful_fetch(self, mock_run):
        """Should return git root directory."""
        mock_result = mock.MagicMock()
        mock_result.stdout = "/path/to/repo\n"
        mock_run.return_value = mock_result

        root = get_git_root()
        assert root == "/path/to/repo"

    @mock.patch("local_review.subprocess.run")
    def test_not_a_git_repo(self, mock_run):
        """Should exit when not in a git repository."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(128, "git")

        with pytest.raises(SystemExit) as exc_info:
            get_git_root()
        assert exc_info.value.code == 1


class TestGetCurrentBranch:
    @mock.patch("local_review.subprocess.run")
    def test_successful_fetch(self, mock_run):
        """Should return current branch name."""
        mock_result = mock.MagicMock()
        mock_result.stdout = "feature/test-branch\n"
        mock_run.return_value = mock_result

        branch = get_current_branch()
        assert branch == "feature/test-branch"

    @mock.patch("local_review.subprocess.run")
    def test_fetch_failure(self, mock_run):
        """Should exit on fetch failure."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        with pytest.raises(SystemExit) as exc_info:
            get_current_branch()
        assert exc_info.value.code == 1


class TestGetLocalDiff:
    @mock.patch("local_review.subprocess.run")
    def test_successful_diff(self, mock_run):
        """Should return diff including staged and unstaged changes."""
        # Mock git diff against main
        diff_result = mock.MagicMock()
        diff_result.stdout = "diff --git a/file1.py b/file1.py\n--- a/file1.py\n+++ b/file1.py\n"

        # Mock git diff HEAD (unstaged)
        unstaged_result = mock.MagicMock()
        unstaged_result.stdout = "diff --git a/file2.py b/file2.py\n--- a/file2.py\n+++ b/file2.py\n"

        # Mock git ls-files (untracked)
        untracked_result = mock.MagicMock()
        untracked_result.stdout = "file3.py\n"

        # Set up side effects for multiple calls
        mock_run.side_effect = [diff_result, unstaged_result, untracked_result]

        diff = get_local_diff("main")
        assert "diff --git a/file1.py" in diff
        assert "diff --git a/file2.py" in diff
        assert "file3.py" in diff

    @mock.patch("local_review.subprocess.run")
    def test_no_changes(self, mock_run):
        """Should return empty diff when no changes."""
        mock_result = mock.MagicMock()
        mock_result.stdout = ""

        mock_run.side_effect = [mock_result, mock_result, mock_result]

        diff = get_local_diff("main")
        assert diff.strip() == ""

    @mock.patch("local_review.subprocess.run")
    def test_git_error(self, mock_run):
        """Should exit on git error."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        with pytest.raises(SystemExit) as exc_info:
            get_local_diff("main")
        assert exc_info.value.code == 1


class TestGenerateMarkdownReport:
    def test_report_format(self):
        """Should generate properly formatted markdown report."""
        review = "## Issues\n\nNo issues found.\n\n**APPROVE**"
        report = generate_markdown_report(
            review=review,
            target_branch="main",
            current_branch="feature/test",
            model="neural-chat",
            diff_size=1500,
            timestamp="2024-01-15T10:30:00+00:00",
        )

        assert "# Local Code Review Report" in report
        assert "**Generated:** 2024-01-15T10:30:00+00:00" in report
        assert "**Current branch:** feature/test" in report
        assert "**Compared against:** main" in report
        assert "**AI Model:** neural-chat" in report
        assert "**Diff size:** 1500 characters" in report
        assert "## Review" in report
        assert "APPROVE" in report

    def test_review_section_preserved(self):
        """Should preserve the full review text."""
        review = "### 1. Acceptance criteria\n✓ All AC met\n\n### 2. Bugs\nNone found"
        report = generate_markdown_report(
            review=review,
            target_branch="develop",
            current_branch="fix/bug-123",
            model="mistral",
            diff_size=2000,
            timestamp="2024-01-15T10:30:00+00:00",
        )

        assert "Acceptance criteria" in report
        assert "None found" in report


class TestSaveReport:
    def test_save_to_file(self, tmp_path):
        """Should save report to specified file."""
        output_file = tmp_path / "test_review.md"
        content = "# Test Report\n\nThis is a test."

        result = save_report(content, str(output_file))

        assert Path(result).exists()
        assert Path(result).read_text() == content

    def test_create_parent_directories(self, tmp_path):
        """Should create parent directories if they don't exist."""
        output_file = tmp_path / "subdir" / "nested" / "report.md"
        content = "# Test"

        result = save_report(content, str(output_file))

        assert Path(result).exists()
        assert Path(result).parent.exists()

    def test_overwrite_existing_file(self, tmp_path):
        """Should overwrite existing file."""
        output_file = tmp_path / "existing.md"
        output_file.write_text("Old content")

        new_content = "# New Report\n\nUpdated content"
        result = save_report(new_content, str(output_file))

        assert Path(result).read_text() == new_content
