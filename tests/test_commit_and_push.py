"""Unit tests for the commit_and_push helper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "developer_tools"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "developer_tools" / "lib"))

from commit_and_push import (  # noqa: E402
    build_commit_prompt,
    commit_changes,
    ensure_issue_reference,
    generate_commit_message,
    get_git_root,
    get_staged_diff,
    has_staged_changes,
    main,
    refuse_if_main_branch,
    stage_changes,
)


class TestRefuseIfMainBranch:
    def test_raises_on_main(self):
        with pytest.raises(SystemExit) as exc_info:
            refuse_if_main_branch("main")
        assert exc_info.value.code == 1

    def test_allows_other_branches(self):
        refuse_if_main_branch("fix/4445-thing")


class TestGetGitRoot:
    @mock.patch("commit_and_push.subprocess.run")
    def test_successful_fetch(self, mock_run):
        mock_result = mock.MagicMock()
        mock_result.stdout = "/path/to/repo\n"
        mock_run.return_value = mock_result

        assert get_git_root() == "/path/to/repo"

    @mock.patch("commit_and_push.subprocess.run")
    def test_not_a_git_repo(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(128, "git")

        with pytest.raises(SystemExit) as exc_info:
            get_git_root()
        assert exc_info.value.code == 1


class TestStageChanges:
    @mock.patch("commit_and_push.subprocess.run")
    def test_stages_specific_files(self, mock_run):
        stage_changes(["a.py", "b.py"])

        mock_run.assert_called_once_with(["git", "add", "--", "a.py", "b.py"], check=True)

    @mock.patch("commit_and_push.subprocess.run")
    def test_stages_all_when_no_files_given(self, mock_run):
        stage_changes(None)

        mock_run.assert_called_once_with(["git", "add", "-A"], check=True)

    @mock.patch("commit_and_push.subprocess.run")
    def test_failure_exits_cleanly(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        with pytest.raises(SystemExit) as exc_info:
            stage_changes(["missing.py"])
        assert exc_info.value.code == 1


class TestHasStagedChanges:
    @mock.patch("commit_and_push.subprocess.run")
    def test_true_when_diff_exit_code_one(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=1)
        assert has_staged_changes() is True

    @mock.patch("commit_and_push.subprocess.run")
    def test_false_when_no_diff(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=0)
        assert has_staged_changes() is False

    @mock.patch("commit_and_push.subprocess.run")
    def test_git_error_raises_instead_of_reporting_changes(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=128)

        with pytest.raises(SystemExit) as exc_info:
            has_staged_changes()
        assert exc_info.value.code == 1


class TestGetStagedDiff:
    @mock.patch("commit_and_push.subprocess.run")
    def test_returns_diff_output(self, mock_run):
        mock_run.return_value = mock.MagicMock(stdout="diff --git a/x b/x\n")
        assert get_staged_diff() == "diff --git a/x b/x\n"

    @mock.patch("commit_and_push.subprocess.run")
    def test_failure_exits_cleanly(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        with pytest.raises(SystemExit) as exc_info:
            get_staged_diff()
        assert exc_info.value.code == 1


class TestBuildCommitPrompt:
    def test_includes_issue_reference_when_present(self):
        prompt = build_commit_prompt("diff --git a/x b/x", 4445)
        assert "#4445" in prompt
        assert "diff --git a/x b/x" in prompt

    def test_no_issue_reference_when_absent(self):
        prompt = build_commit_prompt("diff --git a/x b/x", None)
        assert "No issue is linked" in prompt


class TestGenerateCommitMessage:
    def test_empty_diff_returns_none(self):
        assert generate_commit_message("", 4445, "local") is None

    @mock.patch("commit_and_push.fetch_review")
    def test_returns_stripped_message(self, mock_fetch):
        mock_fetch.return_value = "  Fix the thing  \n"
        result = generate_commit_message("diff", 4445, "local")
        assert result == "Fix the thing"

    @mock.patch("commit_and_push.fetch_review")
    def test_model_failure_returns_none(self, mock_fetch):
        mock_fetch.side_effect = SystemExit(1)
        assert generate_commit_message("diff", 4445, "local") is None


class TestEnsureIssueReference:
    def test_appends_ref_when_missing(self):
        result = ensure_issue_reference("Fix the thing", 4445)
        assert result == "Fix the thing\n\nRefs #4445"

    def test_no_change_when_already_present(self):
        message = "Fix the thing\n\nRefs #4445"
        assert ensure_issue_reference(message, 4445) == message

    def test_no_change_when_no_issue_id(self):
        assert ensure_issue_reference("Fix the thing", None) == "Fix the thing"


class TestCommitChanges:
    @mock.patch("commit_and_push.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = mock.MagicMock()
        assert commit_changes("Fix the thing") is True

    @mock.patch("commit_and_push.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")
        assert commit_changes("Fix the thing") is False


class TestMain:
    @mock.patch("commit_and_push.push_to_remote")
    @mock.patch("commit_and_push.commit_changes")
    @mock.patch("commit_and_push.has_staged_changes")
    @mock.patch("commit_and_push.stage_changes")
    @mock.patch("commit_and_push.extract_issue_id")
    @mock.patch("commit_and_push.get_current_branch")
    @mock.patch("commit_and_push.get_git_root")
    def test_refuses_to_commit_on_main_branch(
        self,
        mock_root,
        mock_branch,
        mock_extract,
        mock_stage,
        mock_has_staged,
        mock_commit,
        mock_push,
    ):
        mock_root.return_value = "/repo"
        mock_branch.return_value = "main"

        with mock.patch("sys.argv", ["commit_and_push.py"]), mock.patch("commit_and_push.os.chdir"):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_stage.assert_not_called()
        mock_commit.assert_not_called()
        mock_push.assert_not_called()

    @mock.patch("commit_and_push.push_to_remote")
    @mock.patch("commit_and_push.commit_changes")
    @mock.patch("commit_and_push.has_staged_changes")
    @mock.patch("commit_and_push.stage_changes")
    @mock.patch("commit_and_push.extract_issue_id")
    @mock.patch("commit_and_push.get_current_branch")
    @mock.patch("commit_and_push.get_git_root")
    def test_no_changes_to_commit(
        self,
        mock_root,
        mock_branch,
        mock_extract,
        mock_stage,
        mock_has_staged,
        mock_commit,
        mock_push,
    ):
        mock_root.return_value = "/repo"
        mock_branch.return_value = "fix/issue-4445-thing"
        mock_extract.return_value = 4445
        mock_has_staged.return_value = False

        with mock.patch("sys.argv", ["commit_and_push.py"]), mock.patch("commit_and_push.os.chdir"):
            result = main()

        assert result == 0
        mock_commit.assert_not_called()
        mock_push.assert_not_called()

    @mock.patch("commit_and_push.push_to_remote")
    @mock.patch("commit_and_push.commit_changes")
    @mock.patch("commit_and_push.has_staged_changes")
    @mock.patch("commit_and_push.stage_changes")
    @mock.patch("commit_and_push.extract_issue_id")
    @mock.patch("commit_and_push.get_current_branch")
    @mock.patch("commit_and_push.get_git_root")
    def test_commits_and_pushes_with_explicit_message(
        self,
        mock_root,
        mock_branch,
        mock_extract,
        mock_stage,
        mock_has_staged,
        mock_commit,
        mock_push,
    ):
        mock_root.return_value = "/repo"
        mock_branch.return_value = "fix/issue-4445-thing"
        mock_extract.return_value = 4445
        mock_has_staged.return_value = True
        mock_commit.return_value = True
        mock_push.return_value = True

        argv = ["commit_and_push.py", "--message", "Fix the thing", "--no-ollama"]
        with mock.patch("sys.argv", argv), mock.patch("commit_and_push.os.chdir"):
            result = main()

        assert result == 0
        mock_commit.assert_called_once()
        committed_message = mock_commit.call_args.args[0]
        assert "Fix the thing" in committed_message
        assert "#4445" in committed_message
        mock_push.assert_called_once_with("fix/issue-4445-thing")

    @mock.patch("commit_and_push.push_to_remote")
    @mock.patch("commit_and_push.commit_changes")
    @mock.patch("commit_and_push.has_staged_changes")
    @mock.patch("commit_and_push.stage_changes")
    @mock.patch("commit_and_push.extract_issue_id")
    @mock.patch("commit_and_push.get_current_branch")
    @mock.patch("commit_and_push.get_git_root")
    def test_forwards_selected_files_to_staging(
        self,
        mock_root,
        mock_branch,
        mock_extract,
        mock_stage,
        mock_has_staged,
        mock_commit,
        mock_push,
    ):
        mock_root.return_value = "/repo"
        mock_branch.return_value = "fix/issue-4445-thing"
        mock_extract.return_value = 4445
        mock_has_staged.return_value = True
        mock_commit.return_value = True
        mock_push.return_value = True

        argv = [
            "commit_and_push.py",
            "--message",
            "Fix the thing",
            "--no-ollama",
            "--files",
            "a.py",
            "b.py",
        ]
        with mock.patch("sys.argv", argv), mock.patch("commit_and_push.os.chdir"):
            result = main()

        assert result == 0
        mock_stage.assert_called_once_with(["a.py", "b.py"])

    @mock.patch("commit_and_push.push_to_remote")
    @mock.patch("commit_and_push.commit_changes")
    @mock.patch("commit_and_push.has_staged_changes")
    @mock.patch("commit_and_push.stage_changes")
    @mock.patch("commit_and_push.extract_issue_id")
    @mock.patch("commit_and_push.get_current_branch")
    @mock.patch("commit_and_push.get_git_root")
    def test_no_push_flag_skips_push(
        self,
        mock_root,
        mock_branch,
        mock_extract,
        mock_stage,
        mock_has_staged,
        mock_commit,
        mock_push,
    ):
        mock_root.return_value = "/repo"
        mock_branch.return_value = "chore/misc"
        mock_extract.return_value = None
        mock_has_staged.return_value = True
        mock_commit.return_value = True

        argv = ["commit_and_push.py", "--message", "Tidy up", "--no-ollama", "--no-push"]
        with mock.patch("sys.argv", argv), mock.patch("commit_and_push.os.chdir"):
            result = main()

        assert result == 0
        mock_push.assert_not_called()

    @mock.patch("commit_and_push.push_to_remote")
    @mock.patch("commit_and_push.commit_changes")
    @mock.patch("commit_and_push.has_staged_changes")
    @mock.patch("commit_and_push.stage_changes")
    @mock.patch("commit_and_push.extract_issue_id")
    @mock.patch("commit_and_push.get_current_branch")
    @mock.patch("commit_and_push.get_git_root")
    def test_commit_failure_exits_nonzero(
        self,
        mock_root,
        mock_branch,
        mock_extract,
        mock_stage,
        mock_has_staged,
        mock_commit,
        mock_push,
    ):
        mock_root.return_value = "/repo"
        mock_branch.return_value = "chore/misc"
        mock_extract.return_value = None
        mock_has_staged.return_value = True
        mock_commit.return_value = False

        argv = ["commit_and_push.py", "--message", "Tidy up", "--no-ollama"]
        with mock.patch("sys.argv", argv), mock.patch("commit_and_push.os.chdir"):
            result = main()

        assert result == 1
        mock_push.assert_not_called()

    @mock.patch("commit_and_push.push_to_remote")
    @mock.patch("commit_and_push.commit_changes")
    @mock.patch("commit_and_push.has_staged_changes")
    @mock.patch("commit_and_push.stage_changes")
    @mock.patch("commit_and_push.extract_issue_id")
    @mock.patch("commit_and_push.get_current_branch")
    @mock.patch("commit_and_push.get_git_root")
    def test_push_failure_exits_nonzero(
        self,
        mock_root,
        mock_branch,
        mock_extract,
        mock_stage,
        mock_has_staged,
        mock_commit,
        mock_push,
    ):
        mock_root.return_value = "/repo"
        mock_branch.return_value = "chore/misc"
        mock_extract.return_value = None
        mock_has_staged.return_value = True
        mock_commit.return_value = True
        mock_push.return_value = False

        argv = ["commit_and_push.py", "--message", "Tidy up", "--no-ollama"]
        with mock.patch("sys.argv", argv), mock.patch("commit_and_push.os.chdir"):
            result = main()

        assert result == 1
        mock_push.assert_called_once_with("chore/misc")
