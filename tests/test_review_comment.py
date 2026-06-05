from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "build_review_comment.sh"
RUN_URL = "https://github.com/example/repo/actions/runs/12345"


def _to_bash_path(p: Path | str) -> str:
    """Convert a Windows path to the form expected by the active bash binary.

    On Linux/macOS the path is returned unchanged. On Windows, Git Bash invoked
    via subprocess uses WSL-style mounts so C:\\... becomes /mnt/c/...
    """
    if platform.system() != "Windows":
        return str(p)
    s = str(p).replace("\\", "/")
    if len(s) >= 2 and s[1] == ":":
        s = "/mnt/" + s[0].lower() + s[2:]
    return s


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.parametrize("provider", ["Claude", "GPT"])
class TestBuildReviewComment:
    def _run(self, body_file: str, provider: str) -> subprocess.CompletedProcess:
        workflow = f"{provider.lower()}-pr-review.yml"
        return subprocess.run(
            ["bash", _to_bash_path(SCRIPT), _to_bash_path(body_file), provider, workflow, RUN_URL],
            capture_output=True,
            text=True,
        )

    def test_non_empty_body_produces_full_review(self, tmp_path, provider):
        body = tmp_path / "body.md"
        body.write_text("This PR looks fine.")
        result = self._run(str(body), provider)
        assert result.returncode == 0
        assert f"## {provider} AI Code Review" in result.stdout
        assert "This PR looks fine." in result.stdout
        assert "Advisory only." in result.stdout
        assert "Failed" not in result.stdout

    def test_empty_body_produces_failure_notice(self, tmp_path, provider):
        body = tmp_path / "body.md"
        body.write_text("")
        result = self._run(str(body), provider)
        assert result.returncode == 0
        assert f"## {provider} AI Code Review - Failed" in result.stdout
        assert RUN_URL in result.stdout

    def test_missing_body_produces_failure_notice(self, tmp_path, provider):
        missing = str(tmp_path / "nonexistent.md")
        result = self._run(missing, provider)
        assert result.returncode == 0
        assert f"## {provider} AI Code Review - Failed" in result.stdout
        assert RUN_URL in result.stdout
