"""Unit tests for scripts/classify_change.py."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "classify_change.py"
spec = importlib.util.spec_from_file_location("classify_change", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(_mod)  # type: ignore[union-attr]

classify_diff = _mod.classify_diff
is_doc_path = _mod.is_doc_path
main = _mod.main


# ---------------------------------------------------------------------------
# is_doc_path
# ---------------------------------------------------------------------------


class TestIsDocPath:
    @pytest.mark.parametrize(
        "path",
        [
            "README.md",
            "docs/CONTRIBUTOR_RUNBOOK.md",
            "nested/docs/notes.txt",
            ".github/ISSUE_TEMPLATE/bug_report.md",
            "LICENSE",
            "LICENSE.txt",
            "CHANGELOG.md",
        ],
    )
    def test_doc_paths(self, path: str) -> None:
        assert is_doc_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "backend/bootstrap/startup.py",
            "backend/requirements.txt",
            "frontend/src/main.tsx",
            ".github/workflows/ci.yml",
            "scripts/run.sh",
        ],
    )
    def test_non_doc_paths(self, path: str) -> None:
        assert is_doc_path(path) is False


# ---------------------------------------------------------------------------
# classify_diff
# ---------------------------------------------------------------------------


class TestClassifyDiff:
    def test_markdown_only_change_is_doc_only(self) -> None:
        diff = """\
diff --git a/docs/CONTRIBUTOR_RUNBOOK.md b/docs/CONTRIBUTOR_RUNBOOK.md
index abc123..def456 100644
--- a/docs/CONTRIBUTOR_RUNBOOK.md
+++ b/docs/CONTRIBUTOR_RUNBOOK.md
@@ -5,0 +6,2 @@
+Some new prose explaining the fast path.
+
"""
        assert classify_diff(diff) is True

    def test_pure_comment_addition_to_python_file_is_doc_only(self) -> None:
        # Mirrors PR #5554: two comment lines added to an otherwise untouched
        # function, no code lines changed.
        diff = """\
diff --git a/backend/bootstrap/startup.py b/backend/bootstrap/startup.py
index abc123..def456 100644
--- a/backend/bootstrap/startup.py
+++ b/backend/bootstrap/startup.py
@@ -10,0 +11,2 @@ SOME_CONST = 5
+# Increased from 5s to 10s because cold-start S3 fetches were timing out.
+# See issue #1234 for details.
"""
        assert classify_diff(diff) is True

    def test_comment_plus_real_code_change_is_not_doc_only(self) -> None:
        diff = """\
diff --git a/backend/bootstrap/startup.py b/backend/bootstrap/startup.py
index abc123..def456 100644
--- a/backend/bootstrap/startup.py
+++ b/backend/bootstrap/startup.py
@@ -10 +11,2 @@ SOME_CONST = 5
-SNAPSHOT_LOAD_TIMEOUT_SECONDS = 5
+# bumped for slow cold starts
+SNAPSHOT_LOAD_TIMEOUT_SECONDS = 10
"""
        assert classify_diff(diff) is False

    def test_typescript_comment_only_change_is_doc_only(self) -> None:
        diff = """\
diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
index abc123..def456 100644
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -20,0 +21,2 @@ export function App() {
+  // TODO: revisit this once the new layout ships.
+  /* placeholder for future JSDoc block */
"""
        assert classify_diff(diff) is True

    def test_blank_line_only_change_is_doc_only(self) -> None:
        diff = """\
diff --git a/backend/bootstrap/startup.py b/backend/bootstrap/startup.py
index abc123..def456 100644
--- a/backend/bootstrap/startup.py
+++ b/backend/bootstrap/startup.py
@@ -10,0 +11 @@ SOME_CONST = 5
+
"""
        assert classify_diff(diff) is True

    def test_requirements_txt_change_is_never_doc_only(self) -> None:
        # .txt has no recognised comment syntax in SAFE_COMMENT_PREFIXES, so
        # even a "# pinned for security" style addition is conservatively
        # treated as unsafe -- requirements files affect runtime behaviour.
        diff = """\
diff --git a/backend/requirements.txt b/backend/requirements.txt
index abc123..def456 100644
--- a/backend/requirements.txt
+++ b/backend/requirements.txt
@@ -1,0 +2 @@
+# pinned for security fix
"""
        assert classify_diff(diff) is False

    def test_new_code_file_is_not_doc_only(self) -> None:
        diff = """\
diff --git a/backend/new_module.py b/backend/new_module.py
new file mode 100644
index 0000000..abc123
--- /dev/null
+++ b/backend/new_module.py
@@ -0,0 +1,2 @@
+def foo():
+    return 42
"""
        assert classify_diff(diff) is False

    def test_new_markdown_file_is_doc_only(self) -> None:
        diff = """\
diff --git a/docs/NEW_GUIDE.md b/docs/NEW_GUIDE.md
new file mode 100644
index 0000000..abc123
--- /dev/null
+++ b/docs/NEW_GUIDE.md
@@ -0,0 +1,2 @@
+# New guide
+Some content.
"""
        assert classify_diff(diff) is True

    def test_binary_file_outside_docs_is_not_doc_only(self) -> None:
        diff = """\
diff --git a/frontend/public/logo.png b/frontend/public/logo.png
new file mode 100644
index 0000000..abcdef1
Binary files /dev/null and b/frontend/public/logo.png differ
"""
        assert classify_diff(diff) is False

    def test_binary_file_inside_docs_is_doc_only(self) -> None:
        diff = """\
diff --git a/docs/images/diagram.png b/docs/images/diagram.png
new file mode 100644
index 0000000..abcdef1
Binary files /dev/null and b/docs/images/diagram.png differ
"""
        assert classify_diff(diff) is True

    def test_permission_only_change_is_not_doc_only(self) -> None:
        diff = """\
diff --git a/scripts/run.sh b/scripts/run.sh
old mode 100644
new mode 100755
"""
        assert classify_diff(diff) is False

    def test_rename_between_doc_paths_is_doc_only(self) -> None:
        diff = """\
diff --git a/docs/OLD_NAME.md b/docs/NEW_NAME.md
similarity index 100%
rename from docs/OLD_NAME.md
rename to docs/NEW_NAME.md
"""
        assert classify_diff(diff) is True

    def test_rename_of_code_file_is_not_doc_only(self) -> None:
        diff = """\
diff --git a/backend/old_module.py b/backend/new_module.py
similarity index 100%
rename from backend/old_module.py
rename to backend/new_module.py
"""
        assert classify_diff(diff) is False

    def test_multi_file_diff_is_doc_only_only_if_every_file_is_safe(self) -> None:
        diff = """\
diff --git a/docs/CONTRIBUTOR_RUNBOOK.md b/docs/CONTRIBUTOR_RUNBOOK.md
index abc123..def456 100644
--- a/docs/CONTRIBUTOR_RUNBOOK.md
+++ b/docs/CONTRIBUTOR_RUNBOOK.md
@@ -5,0 +6 @@
+Some doc prose.
diff --git a/backend/bootstrap/startup.py b/backend/bootstrap/startup.py
index abc123..def456 100644
--- a/backend/bootstrap/startup.py
+++ b/backend/bootstrap/startup.py
@@ -10 +10 @@ SOME_CONST = 5
-SOME_CONST = 5
+SOME_CONST = 6
"""
        assert classify_diff(diff) is False

    def test_empty_diff_is_doc_only(self) -> None:
        assert classify_diff("") is True


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_non_pull_request_event_skips_diffing_and_is_not_doc_only(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def fail_if_called(base: str, head: str) -> str:
            raise AssertionError("get_diff_text should not be called for push events")

        monkeypatch.setattr(_mod, "get_diff_text", fail_if_called)
        exit_code = main(["--event-name", "push", "--base", "abc", "--head", "def"])
        assert exit_code == 0
        assert "doc-only=false" in capsys.readouterr().out

    def test_pull_request_event_writes_github_output(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(_mod, "get_diff_text", lambda base, head: "")
        output_file = tmp_path / "github_output.txt"
        exit_code = main(
            [
                "--event-name",
                "pull_request",
                "--base",
                "base-sha",
                "--head",
                "head-sha",
                "--github-output",
                str(output_file),
            ]
        )
        assert exit_code == 0
        assert output_file.read_text(encoding="utf-8") == "doc-only=true\n"

    def test_diff_failure_falls_back_to_not_doc_only(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def raise_called_process_error(base: str, head: str) -> str:
            raise subprocess.CalledProcessError(1, ["git", "diff"])

        monkeypatch.setattr(_mod, "get_diff_text", raise_called_process_error)
        exit_code = main(["--event-name", "pull_request", "--base", "abc", "--head", "def"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "doc-only=false" in captured.out
        assert "WARNING" in captured.err
