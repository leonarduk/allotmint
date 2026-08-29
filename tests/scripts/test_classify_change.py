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
areas_for_path = _mod.areas_for_path
areas_for_diff = _mod.areas_for_diff
backend_dev_tools_only = _mod.backend_dev_tools_only
classify = _mod.classify
AREAS = _mod.AREAS


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

    def test_permission_change_on_doc_path_is_not_doc_only(self) -> None:
        diff = """\
diff --git a/docs/DEPLOY.md b/docs/DEPLOY.md
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
        written = output_file.read_text(encoding="utf-8").splitlines()
        # An empty diff is doc-only, so every area flag (and the narrow
        # dev-tools flag) must be false.
        assert written[0] == "doc-only=true"
        assert sorted(written[1:]) == sorted([*(f"{area}=false" for area in AREAS), "backend-dev-tools-only=false"])

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

    def test_every_area_flag_is_emitted_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A missing output line would leave a gated job with an empty flag.

        `!= 'false'` means that fails safe (the job runs), but silently, so
        assert the full set is always present rather than relying on it.
        """
        monkeypatch.setattr(_mod, "get_diff_text", lambda base, head: "")
        exit_code = main(["--event-name", "pull_request", "--base", "a", "--head", "b"])
        assert exit_code == 0
        printed = capsys.readouterr().out.splitlines()
        keys = [line.split("=", 1)[0] for line in printed]
        assert keys == ["doc-only", *AREAS, "backend-dev-tools-only"]


# ---------------------------------------------------------------------------
# areas_for_path
# ---------------------------------------------------------------------------


class TestAreasForPath:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            # Backend
            ("backend/app.py", {"backend"}),
            ("backend/routes/accounts.py", {"backend"}),
            ("tests/test_backend_api.py", {"backend"}),
            ("tests/scripts/test_publish_pr.py", {"backend"}),
            ("requirements.txt", {"backend"}),
            ("requirements-dev.txt", {"backend"}),
            ("mypy.ini", {"backend"}),
            ("pyproject.toml", {"backend"}),
            ("config.yaml", {"backend"}),
            ("scripts/site_healthcheck.py", {"backend"}),
            ("data/accounts/demo.json", {"backend"}),
            # Frontend
            ("frontend/src/main.tsx", {"frontend"}),
            ("frontend/package-lock.json", {"frontend"}),
            # CDK
            ("cdk/stacks/api_stack.py", {"cdk"}),
            ("cdk/tests/test_api_stack.py", {"cdk"}),
            ("infra/lambda/handler.py", {"cdk"}),
            # Shell / container / deploy
            ("scripts/bash/run-local-api.sh", {"shell"}),
            ("tests/bash/fetch-cloudwatch-logs.bats", {"shell"}),
            ("Dockerfile", {"shell"}),
            ("backend/Dockerfile.lambda", {"shell"}),
            ("docker/nginx/nginx.conf", {"shell"}),
            ("docker-compose.local.yml", {"shell"}),
            ("deploy/Jenkinsfile-deploy", {"shell"}),
            ("Jenkinsfile", {"shell"}),
            # PowerShell scripts have no dedicated area (no Pester suite in the
            # repo); they fall through to the scripts/** -> backend catch-all.
            ("scripts/powershell/aider-issue.ps1", {"backend"}),
            ("scripts/reconcile_drawdown.py", {"backend"}),
        ],
    )
    def test_single_area_paths(self, path: str, expected: set[str]) -> None:
        assert set(areas_for_path(path)) == expected

    @pytest.mark.parametrize(
        "path",
        ["docs/DEPLOY.md", "README.md", "frontend/README.md", "LICENSE", ".github/ISSUE_TEMPLATE/bug_report.md"],
    )
    def test_documentation_paths_affect_no_area(self, path: str) -> None:
        assert areas_for_path(path) == frozenset()

    @pytest.mark.parametrize(
        "path",
        [
            ".github/workflows/ci.yml",
            ".github/workflows/_classify-change.yml",
            ".github/actions/setup-frontend-deps/action.yml",
            ".github/rulesets/default-branch-protection.json",
            # .github/scripts/*.sh are invoked by workflows, so they widen to
            # everything under the `.github/**` rule rather than being treated
            # as ordinary shell scripts.
            ".github/scripts/extract_verdict.sh",
            "scripts/classify_change.py",
            "scripts/check_branch_protection_required_checks.py",
        ],
    )
    def test_ci_machinery_widens_to_every_area(self, path: str) -> None:
        """A change to the gating itself must never narrow the suite that validates it."""
        assert set(areas_for_path(path)) == set(AREAS)

    def test_unmapped_path_falls_back_to_every_area(self) -> None:
        """The fail-safe: a new top-level directory can't silently skip everything."""
        assert set(areas_for_path("some-brand-new-top-level-dir/thing.go")) == set(AREAS)

    def test_root_package_files_are_frontend_and_cdk(self) -> None:
        """Root npm installs the CDK CLI that `cdk synth` invokes, not just JS deps."""
        assert set(areas_for_path("package.json")) == {"frontend", "cdk"}
        assert set(areas_for_path("package-lock.json")) == {"frontend", "cdk"}

    def test_contracts_spa_is_backend_and_frontend(self) -> None:
        """check_contract_version_sync.py asserts this module against the SPA."""
        assert set(areas_for_path("backend/contracts_spa.py")) == {"backend", "frontend"}

    def test_trading_agent_is_backend_and_frontend(self) -> None:
        """frontend/tests/unit/pages/Trading.test.tsx (#7230) pins the
        checks_skipped vocabulary this module emits against frontend copy --
        a backend-only PR that changes it must still run the frontend suite."""
        assert set(areas_for_path("backend/agent/trading_agent.py")) == {"backend", "frontend"}

    def test_narrow_rules_win_over_the_broader_rules_they_sit_inside(self) -> None:
        # tests/bash/** must not be swallowed by tests/** -> backend.
        assert set(areas_for_path("tests/bash/deploy.bats")) == {"shell"}
        # ...while its general case still lands on backend.
        assert set(areas_for_path("tests/test_app.py")) == {"backend"}
        assert set(areas_for_path("scripts/check_contract_version_sync.py")) == {"backend"}

    def test_matching_is_case_insensitive(self) -> None:
        assert areas_for_path("Docs/Guide.MD") == frozenset()
        assert set(areas_for_path("Frontend/src/App.tsx")) == {"frontend"}


# ---------------------------------------------------------------------------
# areas_for_diff
# ---------------------------------------------------------------------------


class TestAreasForDiff:
    def test_multi_area_diff_unions_areas(self) -> None:
        diff = """\
diff --git a/backend/app.py b/backend/app.py
index abc123..def456 100644
--- a/backend/app.py
+++ b/backend/app.py
@@ -1 +1 @@
-x = 1
+x = 2
diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
index abc123..def456 100644
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -1 +1 @@
-const a = 1
+const a = 2
"""
        assert set(areas_for_diff(diff)) == {"backend", "frontend"}

    def test_rename_counts_both_old_and_new_paths(self) -> None:
        """Moving a file out of an area must still run that area's suite."""
        diff = """\
diff --git a/backend/helper.py b/frontend/src/helper.ts
similarity index 90%
rename from backend/helper.py
rename to frontend/src/helper.ts
"""
        assert set(areas_for_diff(diff)) == {"backend", "frontend"}

    def test_empty_diff_affects_no_area(self) -> None:
        assert areas_for_diff("") == frozenset()


# ---------------------------------------------------------------------------
# backend_dev_tools_only
# ---------------------------------------------------------------------------


class TestBackendDevToolsOnly:
    def test_script_test_change_is_narrow(self) -> None:
        diff = """\
diff --git a/tests/scripts/test_widget.py b/tests/scripts/test_widget.py
--- a/tests/scripts/test_widget.py
+++ b/tests/scripts/test_widget.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
        assert backend_dev_tools_only(diff) is True

    def test_backend_module_change_is_not_narrow(self) -> None:
        diff = """\
diff --git a/backend/app.py b/backend/app.py
--- a/backend/app.py
+++ b/backend/app.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
        assert backend_dev_tools_only(diff) is False


class TestClassify:
    def test_non_pull_request_event_affects_every_area(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """push to main must keep running the full suite."""

        def fail_if_called(base: str, head: str) -> str:
            raise AssertionError("get_diff_text should not be called for push events")

        monkeypatch.setattr(_mod, "get_diff_text", fail_if_called)
        doc_only, areas, narrow = classify("push", "abc", "def")
        assert doc_only is False
        assert set(areas) == set(AREAS)
        assert narrow is False

    @pytest.mark.parametrize(("base", "head"), [("", "head-sha"), ("base-sha", ""), ("", "")])
    def test_missing_sha_affects_every_area(self, monkeypatch: pytest.MonkeyPatch, base: str, head: str) -> None:
        monkeypatch.setattr(
            _mod,
            "get_diff_text",
            lambda b, h: (_ for _ in ()).throw(AssertionError("should not diff without both SHAs")),
        )
        _, areas, narrow = classify("pull_request", base, head)
        assert set(areas) == set(AREAS)
        assert narrow is False

    def test_diff_failure_affects_every_area(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def raise_called_process_error(base: str, head: str) -> str:
            raise subprocess.CalledProcessError(1, ["git", "diff"])

        monkeypatch.setattr(_mod, "get_diff_text", raise_called_process_error)
        doc_only, areas, narrow = classify("pull_request", "abc", "def")
        assert doc_only is False
        assert set(areas) == set(AREAS)
        assert narrow is False

    def test_doc_only_diff_zeroes_every_area(self, monkeypatch: pytest.MonkeyPatch) -> None:
        diff = """\
diff --git a/docs/RUNBOOK.md b/docs/RUNBOOK.md
index abc123..def456 100644
--- a/docs/RUNBOOK.md
+++ b/docs/RUNBOOK.md
@@ -1,0 +2 @@
+Some prose.
"""
        monkeypatch.setattr(_mod, "get_diff_text", lambda base, head: diff)
        doc_only, areas, narrow = classify("pull_request", "abc", "def")
        assert doc_only is True
        assert areas == frozenset()
        assert narrow is False

    def test_comment_only_python_change_zeroes_areas_despite_backend_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """doc-only wins over the path map, so jobs gate on one flag only."""
        diff = """\
diff --git a/backend/app.py b/backend/app.py
index abc123..def456 100644
--- a/backend/app.py
+++ b/backend/app.py
@@ -10,0 +11 @@ SOME_CONST = 5
+# Explanatory comment only.
"""
        monkeypatch.setattr(_mod, "get_diff_text", lambda base, head: diff)
        doc_only, areas, narrow = classify("pull_request", "abc", "def")
        assert doc_only is True
        assert areas == frozenset()
        assert narrow is False

    def test_backend_only_change_does_not_affect_frontend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        diff = """\
diff --git a/backend/routes/accounts.py b/backend/routes/accounts.py
index abc123..def456 100644
--- a/backend/routes/accounts.py
+++ b/backend/routes/accounts.py
@@ -1 +1 @@
-LIMIT = 10
+LIMIT = 20
"""
        monkeypatch.setattr(_mod, "get_diff_text", lambda base, head: diff)
        doc_only, areas, narrow = classify("pull_request", "abc", "def")
        assert doc_only is False
        assert set(areas) == {"backend"}
        assert narrow is False

    def test_frontend_only_change_does_not_affect_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        diff = """\
diff --git a/frontend/src/pages/Market.tsx b/frontend/src/pages/Market.tsx
index abc123..def456 100644
--- a/frontend/src/pages/Market.tsx
+++ b/frontend/src/pages/Market.tsx
@@ -1 +1 @@
-const a = 1
+const a = 2
"""
        monkeypatch.setattr(_mod, "get_diff_text", lambda base, head: diff)
        _, areas, narrow = classify("pull_request", "abc", "def")
        assert set(areas) == {"frontend"}
        assert narrow is False

    def test_powershell_only_change_falls_back_to_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No dedicated area for .ps1 (no Pester suite); falls to scripts/** -> backend."""
        diff = """\
diff --git a/scripts/powershell/aider-issue.ps1 b/scripts/powershell/aider-issue.ps1
index abc123..def456 100644
--- a/scripts/powershell/aider-issue.ps1
+++ b/scripts/powershell/aider-issue.ps1
@@ -1 +1 @@
-$x = 1
+$x = 2
"""
        monkeypatch.setattr(_mod, "get_diff_text", lambda base, head: diff)
        _, areas, narrow = classify("pull_request", "abc", "def")
        assert set(areas) == {"backend"}
        assert narrow is False

    def test_workflow_change_affects_every_area(self, monkeypatch: pytest.MonkeyPatch) -> None:
        diff = """\
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index abc123..def456 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1 +1 @@
-  runs-on: ubuntu-latest
+  runs-on: ubuntu-24.04
"""
        monkeypatch.setattr(_mod, "get_diff_text", lambda base, head: diff)
        _, areas, narrow = classify("pull_request", "abc", "def")
        assert set(areas) == set(AREAS)
        assert narrow is False

    def test_script_tests_only_change_sets_narrow_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        diff = """\
diff --git a/tests/scripts/test_widget.py b/tests/scripts/test_widget.py
--- a/tests/scripts/test_widget.py
+++ b/tests/scripts/test_widget.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
        monkeypatch.setattr(_mod, "get_diff_text", lambda base, head: diff)
        doc_only, areas, narrow = classify("pull_request", "abc", "def")
        assert doc_only is False
        assert set(areas) == {"backend"}
        assert narrow is True
