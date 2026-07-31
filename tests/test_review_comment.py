from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "build_review_comment.sh"
RUN_URL = "https://github.com/example/repo/actions/runs/12345"

# Common Git-for-Windows install locations, checked when PATH search finds
# only the WSL launcher stub (see _find_bash below).
_GIT_BASH_CANDIDATES = [
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
]


def _is_git_bash(candidate: str) -> bool:
    """Distinguish Git Bash (MSYS) from a WSL launcher stub by version banner.

    Windows ships several ``bash.exe`` launchers that hand off to WSL (under
    ``System32`` and under the WindowsApps alias directory) -- both report a
    ``x86_64-pc-linux-gnu`` platform tag and mount drives at ``/mnt/c/...``,
    unlike Git Bash's ``x86_64-pc-msys`` and ``/c/...``. Path-substring checks
    (e.g. skipping anything under "System32") don't catch the WindowsApps
    stub, so check the actual banner instead of guessing from the path.
    """
    try:
        result = subprocess.run(
            [candidate, "--version"], capture_output=True, text=True, timeout=10
        )
    except OSError:
        return False
    return result.returncode == 0 and "msys" in result.stdout.lower()


def _find_bash() -> str | None:
    """Locate a real bash binary, skipping Windows' WSL launcher stubs."""
    if platform.system() != "Windows":
        return shutil.which("bash")
    seen: set[str] = set()
    candidates: list[str] = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        for name in ("bash.exe", "bash"):
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate) and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    candidates.extend(c for c in _GIT_BASH_CANDIDATES if os.path.isfile(c))
    for candidate in candidates:
        if _is_git_bash(candidate):
            return candidate
    return shutil.which("bash")


BASH = _find_bash()


def _to_bash_path(p: Path | str) -> str:
    """Convert a Windows path to the form expected by Git Bash (MSYS).

    On Linux/macOS the path is returned unchanged. Git Bash on Windows accepts
    native "C:/..." paths directly (with forward slashes), so no drive-letter
    remapping is needed -- unlike WSL's bash, which mounts drives at /mnt/c/...
    """
    if platform.system() != "Windows":
        return str(p)
    return str(p).replace("\\", "/")


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("provider", ["Claude", "GPT"])
class TestBuildReviewComment:
    def _run(self, body_file: str, provider: str) -> subprocess.CompletedProcess:
        workflow = f"{provider.lower()}-pr-review.yml"
        return subprocess.run(
            # Resolve bash to its full path rather than relying on PATH search:
            # subprocess on Windows can hand a POSIX-style PATH to CreateProcess,
            # which fails to parse it and falls back to system dirs, silently
            # picking up the WSL launcher stub at System32\bash.exe instead of
            # Git Bash -- a different shell with different path conventions.
            [BASH, _to_bash_path(SCRIPT), _to_bash_path(body_file), provider, workflow, RUN_URL],
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
