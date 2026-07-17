"""Unit tests for publish_pr script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "dev_tools"))
from publish_pr import check_gh_available


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
