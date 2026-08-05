"""Unit tests for the aider issue extractor script."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "developer_tools"))

from f_implement_issue_with_aider import (  # noqa: E402
    _normalize_symbol_prefix,
    confirm_with_user,
    extract_file_paths_from_issue,
    fetch_issue_from_github,
    formulate_aider_prompt,
    graphify_hint_for_files,
    is_safe_relative_path,
    load_graphify_analysis,
    load_issue_from_file,
    main,
    parse_issue_body,
    resolve_files_to_edit,
    run_aider,
    suggest_files_with_ollama,
)

ISSUE_BODY = """## What

Do the thing.

## Why

Because it matters.

## How

1. Step one.
2. Step two.

## Constraints

Must not break anything.

## Success looks like

- It works.

## Failure looks like

It doesn't work.
"""


class TestParseIssueBody:
    def test_extracts_all_known_sections(self):
        sections = parse_issue_body(ISSUE_BODY)
        assert sections["what"] == "Do the thing."
        assert sections["why"] == "Because it matters."
        assert "Step one." in sections["how"]
        assert sections["constraints"] == "Must not break anything."
        assert sections["success"] == "- It works."
        assert sections["failure"] == "It doesn't work."

    def test_returns_empty_dict_for_unstructured_body(self):
        assert parse_issue_body("Just a plain sentence with no headers.") == {}

    def test_ignores_unrecognized_sections(self):
        body = "## Random Heading\n\nSome content.\n"
        assert parse_issue_body(body) == {}

    def test_extracts_files_affected_section(self):
        body = "## Files Affected\n\nbackend/app.py\nfrontend/src/main.tsx\n"
        sections = parse_issue_body(body)
        assert sections["files_affected"] == "backend/app.py\nfrontend/src/main.tsx"

    def test_extracts_bold_headers_not_just_atx(self):
        # Issues filed before the "## Heading" template was standardized (or
        # edited by hand) use whole-line "**Heading**" bold style instead.
        body = "**What**\nDo the thing.\n\n**Files to change**\nbackend/app.py\n"
        sections = parse_issue_body(body)
        assert sections["what"] == "Do the thing."
        assert sections["files_affected"] == "backend/app.py"


class TestIsSafeRelativePath:
    def test_rejects_parent_traversal(self):
        assert is_safe_relative_path("../secret.py") is False
        assert is_safe_relative_path("a/../../b.py") is False

    def test_rejects_absolute_paths(self):
        assert is_safe_relative_path("/etc/passwd") is False

    def test_accepts_plain_relative_path(self):
        assert is_safe_relative_path("scripts/developer_tools/f_implement_issue_with_aider.py") is True


class TestExtractFilePathsFromIssue:
    def test_finds_existing_file_path(self):
        real_file = "scripts/developer_tools/f_implement_issue_with_aider.py"
        body = f"See {real_file} for details."
        paths = extract_file_paths_from_issue(body)
        assert real_file in paths

    def test_ignores_paths_that_do_not_exist(self):
        body = "See totally/made/up/path.py for details."
        assert extract_file_paths_from_issue(body) == []

    def test_returns_empty_list_when_no_paths_mentioned(self):
        assert extract_file_paths_from_issue("No files mentioned here.") == []

    def test_rejects_traversal_path_even_when_it_resolves_to_a_real_file(self):
        # This resolves on disk to the same file as the "finds_existing_file_path"
        # test above, but the raw path contains a '..' segment, which must be
        # rejected before the existence check ever runs.
        body = "See scripts/../scripts/developer_tools/f_implement_issue_with_aider.py for details."
        assert extract_file_paths_from_issue(body) == []

    def test_finds_path_inside_markdown_link(self):
        real_file = "scripts/developer_tools/f_implement_issue_with_aider.py"
        body = f"- [{real_file}](https://github.com/owner/repo/blob/main/{real_file}) - details."
        paths = extract_file_paths_from_issue(body)
        assert paths == [real_file]

    def test_does_not_truncate_tsx_extension_to_ts(self):
        real_file = "frontend/src/components/Menu.tsx"
        body = f"See {real_file} for details."
        assert extract_file_paths_from_issue(body) == [real_file]

    def test_does_not_truncate_jsx_extension_to_js(self):
        # No .jsx fixture exists in-repo, so exercise the regex directly
        # rather than depending on Path.exists() filtering.
        pattern = r"(?:^|[\s\[\(`])([a-zA-Z0-9._/\-]+\.(?:tsx|ts|py|jsx|js|css|md|yaml|yml|json))"
        match = re.search(pattern, "See src/components/Foo.jsx for details.")
        assert match.group(1) == "src/components/Foo.jsx"

    def test_finds_path_wrapped_in_backticks(self):
        # Regression test: this repo's issue template renders "Files Affected"
        # as a bullet list of backtick-wrapped paths, e.g. "- `backend/app.py`"
        # -- previously the lookback character class didn't include a backtick,
        # so this exact, standard format was never matched and every
        # well-formed issue produced zero extracted files (discovered via #5850).
        real_file = "scripts/developer_tools/f_implement_issue_with_aider.py"
        body = f"## Files Affected\n- `{real_file}`\n"
        assert extract_file_paths_from_issue(body) == [real_file]

    def test_finds_multiple_backtick_wrapped_paths_in_bullet_list(self):
        file_a = "scripts/developer_tools/f_implement_issue_with_aider.py"
        file_b = "scripts/developer_tools/b_create_issue.py"
        body = f"## Files Affected\n- `{file_a}`\n- `{file_b}`\n"
        assert set(extract_file_paths_from_issue(body)) == {file_a, file_b}

    def test_backtick_wrapped_path_with_space_is_not_matched(self):
        """Paths containing a space are outside the supported character class (#5852).

        The path regex's character class ([a-zA-Z0-9._/\\-]+) deliberately
        excludes whitespace, so a backtick-wrapped path with an embedded
        space (e.g. from a file genuinely named with a space) is not
        extracted. This pins down that known, intentional limitation rather
        than leaving it undocumented.
        """
        body = "## Files Affected\n- `scripts/my script/f_implement_issue_with_aider.py`\n"
        assert extract_file_paths_from_issue(body) == []

    def test_backtick_wrapped_path_with_special_characters_is_not_matched(self):
        """Paths with characters outside [a-zA-Z0-9._/-] are not extracted (#5852)."""
        body = "## Files Affected\n- `scripts/weird(name)/f_implement_issue_with_aider.py`\n"
        assert extract_file_paths_from_issue(body) == []


class TestResolveFilesToEdit:
    def test_prefers_files_affected_section_over_whole_body(self):
        real_file = "scripts/developer_tools/f_implement_issue_with_aider.py"
        other_file = "scripts/developer_tools/b_create_issue.py"
        body = f"See {other_file} for background."

        result = resolve_files_to_edit("title", body, "http://x", "model", files_affected=real_file)
        assert result == [real_file]

    @mock.patch("f_implement_issue_with_aider.fetch_ollama_review")
    def test_falls_back_to_body_when_files_affected_has_no_real_paths(self, mock_fetch):
        real_file = "scripts/developer_tools/f_implement_issue_with_aider.py"
        body = f"See {real_file} for details."

        result = resolve_files_to_edit("title", body, "http://x", "model", files_affected="totally/made/up/path.py")
        assert result == [real_file]
        mock_fetch.assert_not_called()

    @mock.patch("f_implement_issue_with_aider.fetch_ollama_review")
    def test_asks_ollama_when_nothing_found_anywhere(self, mock_fetch):
        mock_fetch.return_value = "[]"

        result = resolve_files_to_edit("title", "no files here", "http://x", "model", files_affected="also none here")
        assert result == []
        mock_fetch.assert_called_once()

    @mock.patch("f_implement_issue_with_aider.fetch_ollama_review")
    def test_resolves_backtick_wrapped_files_affected_bullet_without_ollama(self, mock_fetch):
        # Regression test for #5850: the standard "## Files Affected\n- `path`"
        # bullet format (the actual template convention used across every issue
        # in this repo) previously matched nothing, so a well-formed issue fell
        # through to Ollama and still produced an empty file list.
        real_file = "scripts/developer_tools/f_implement_issue_with_aider.py"
        body = f"## What\nDo the thing.\n\n## Files Affected\n- `{real_file}`\n"
        sections = parse_issue_body(body)

        result = resolve_files_to_edit(
            "title", body, "http://x", "model", files_affected=sections.get("files_affected", "")
        )
        assert result == [real_file]
        mock_fetch.assert_not_called()

    @mock.patch("f_implement_issue_with_aider.fetch_ollama_review")
    def test_resolves_files_from_bold_header_markdown_link_issue_without_ollama(self, mock_fetch):
        # Regression test for #5798: issues written before the "## Heading"
        # template was standardized use bold "**Heading**" lines and list
        # files as markdown links, e.g. "[path](url)". Previously this fell
        # through to Ollama and produced an empty file list.
        real_file = "scripts/developer_tools/f_implement_issue_with_aider.py"
        body = (
            "**What**\nSomething is broken.\n\n"
            "**Files to change**\n"
            f"- [{real_file}](https://github.com/owner/repo/blob/main/{real_file})"
            " - relevant logic here.\n\n"
            "**Constraints**\nNone.\n"
        )
        sections = parse_issue_body(body)

        result = resolve_files_to_edit(
            "title", body, "http://x", "model", files_affected=sections.get("files_affected", "")
        )
        assert result == [real_file]
        mock_fetch.assert_not_called()


class TestNormalizeSymbolPrefix:
    def test_converts_path_to_underscore_prefix(self):
        assert _normalize_symbol_prefix("backend/app.py") == "backend_app"

    def test_strips_extension_and_lowercases(self):
        assert _normalize_symbol_prefix("frontend/src/api.ts") == "frontend_src_api"

    def test_collapses_non_alnum_runs(self):
        assert _normalize_symbol_prefix("scripts/dev-tools/f_foo.py") == "scripts_dev_tools_f_foo"


class TestLoadGraphifyAnalysis:
    def test_returns_none_when_file_missing(self, tmp_path):
        assert load_graphify_analysis(str(tmp_path / "nope.json")) is None

    def test_returns_none_on_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        assert load_graphify_analysis(str(bad)) is None

    def test_loads_valid_json(self, tmp_path):
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text(json.dumps({"gods": [], "communities": {}}))
        assert load_graphify_analysis(str(analysis_file)) == {"gods": [], "communities": {}}


class TestGraphifyHintForFiles:
    def test_returns_empty_string_when_analysis_is_none(self):
        assert graphify_hint_for_files(["backend/app.py"], None) == ""

    def test_returns_empty_string_when_analysis_has_no_matches(self):
        analysis = {
            "gods": [{"id": "unrelated_symbol", "label": "x()", "degree": 5}],
            "communities": {},
        }
        assert graphify_hint_for_files(["backend/app.py"], analysis) == ""

    def test_returns_empty_string_for_empty_analysis(self):
        assert graphify_hint_for_files(["backend/app.py"], {}) == ""

    def test_flags_god_object_hotspot(self):
        analysis = {
            "gods": [{"id": "backend_app_create_app", "label": "create_app()", "degree": 224}],
            "communities": {},
        }
        hint = graphify_hint_for_files(["backend/app.py"], analysis)
        assert "backend/app.py" in hint
        assert "create_app()" in hint
        assert "224" in hint

    def test_flags_community_membership(self):
        analysis = {
            "gods": [],
            "communities": {"5": ["frontend_src_api", "frontend_src_api_foo", "other_symbol"]},
        }
        hint = graphify_hint_for_files(["frontend/src/api.ts"], analysis)
        assert "frontend/src/api.ts" in hint
        assert "community 5" in hint
        assert "2 other symbols" in hint


class TestFormulateAiderPrompt:
    def test_includes_title_and_sections(self):
        sections = {"what": "Do the thing.", "how": "Do it this way."}
        prompt = formulate_aider_prompt("Issue Title", sections)
        assert prompt.startswith("Issue Title")
        assert "What:" in prompt
        assert "Do the thing." in prompt
        assert "How:" in prompt
        assert "Do it this way." in prompt

    def test_omits_missing_sections(self):
        prompt = formulate_aider_prompt("Issue Title", {"what": "Only this."})
        assert "How:" not in prompt
        assert "Constraints:" not in prompt
        assert "Success:" not in prompt

    def test_skips_blank_sections(self):
        prompt = formulate_aider_prompt("Issue Title", {"what": "   "})
        assert "What:" not in prompt

    def test_excludes_why_files_affected_and_failure(self):
        # These sections are deliberately dropped: "why" isn't actionable,
        # "files_affected" duplicates the file list already loaded into
        # aider's context, and "failure" is just the inverse of "success".
        sections = {
            "what": "Do the thing.",
            "why": "Because reasons.",
            "files_affected": "backend/app.py",
            "success": "It works.",
            "failure": "It doesn't work.",
        }
        prompt = formulate_aider_prompt("Issue Title", sections)
        assert "Why:" not in prompt
        assert "Files Affected:" not in prompt
        assert "backend/app.py" not in prompt
        assert "Failure:" not in prompt
        assert "It doesn't work." not in prompt
        assert "Success:" in prompt

    def test_appends_graphify_hint_when_provided(self):
        prompt = formulate_aider_prompt("Issue Title", {"what": "Do it."}, graphify_hint="\nGraphify hints:\n- foo")
        assert prompt.endswith("Graphify hints:\n- foo")

    def test_omits_graphify_hint_when_empty(self):
        prompt = formulate_aider_prompt("Issue Title", {"what": "Do it."}, graphify_hint="")
        assert "Graphify" not in prompt


class TestFetchIssueFromGithub:
    @mock.patch("f_implement_issue_with_aider.requests.get")
    def test_returns_title_and_body_on_success(self, mock_get):
        mock_response = mock.MagicMock()
        mock_response.json.return_value = {"title": "Bug title", "body": "Bug body"}
        mock_get.return_value = mock_response

        title, body = fetch_issue_from_github("owner", "repo", 42)
        assert title == "Bug title"
        assert body == "Bug body"

    @mock.patch("f_implement_issue_with_aider.requests.get")
    def test_exits_when_issue_has_no_title(self, mock_get):
        mock_response = mock.MagicMock()
        mock_response.json.return_value = {"title": "", "body": "Bug body"}
        mock_get.return_value = mock_response

        with pytest.raises(SystemExit) as exc_info:
            fetch_issue_from_github("owner", "repo", 42)
        assert exc_info.value.code == 1

    @mock.patch("f_implement_issue_with_aider.requests.get")
    def test_exits_on_request_failure(self, mock_get):
        import requests

        mock_get.side_effect = requests.RequestException("network down")

        with pytest.raises(SystemExit) as exc_info:
            fetch_issue_from_github("owner", "repo", 42)
        assert exc_info.value.code == 1


class TestLoadIssueFromFile:
    def test_splits_title_and_body(self, tmp_path):
        issue_file = tmp_path / "issue.md"
        issue_file.write_text("My Title\n\nBody line one.\nBody line two.\n")

        title, body = load_issue_from_file(str(issue_file))
        assert title == "My Title"
        assert "Body line one." in body

    def test_exits_when_file_missing(self):
        with pytest.raises(SystemExit) as exc_info:
            load_issue_from_file("no/such/file.md")
        assert exc_info.value.code == 1


class TestSuggestFilesWithOllama:
    @mock.patch("f_implement_issue_with_aider.fetch_ollama_review")
    def test_parses_json_array_from_response(self, mock_fetch):
        real_file = "scripts/developer_tools/f_implement_issue_with_aider.py"
        mock_fetch.return_value = f'Here you go: ["{real_file}"]'

        result = suggest_files_with_ollama("title", "body", [], "http://x", "model")
        assert result == [real_file]

    @mock.patch("f_implement_issue_with_aider.fetch_ollama_review")
    def test_falls_back_to_extracted_paths_when_ollama_fails(self, mock_fetch):
        mock_fetch.side_effect = SystemExit(1)

        result = suggest_files_with_ollama("title", "body", ["existing.py"], "http://x", "model")
        assert result == ["existing.py"]

    @mock.patch("f_implement_issue_with_aider.fetch_ollama_review")
    def test_falls_back_when_response_has_no_json(self, mock_fetch):
        mock_fetch.return_value = "no json here"

        result = suggest_files_with_ollama("title", "body", ["existing.py"], "http://x", "model")
        assert result == ["existing.py"]

    @mock.patch("f_implement_issue_with_aider.fetch_ollama_review")
    def test_rejects_traversal_path_in_suggested_json(self, mock_fetch):
        traversal_path = "scripts/../scripts/developer_tools/f_implement_issue_with_aider.py"
        mock_fetch.return_value = f'["{traversal_path}"]'

        result = suggest_files_with_ollama("title", "body", [], "http://x", "model")
        assert result == []


class TestConfirmWithUser:
    def test_no_confirm_flag_skips_prompt(self, capsys):
        assert confirm_with_user(["file.py"], "prompt text", no_confirm=True) is True

    def test_eof_on_input_is_treated_as_declined(self, monkeypatch):
        def _raise_eof():
            raise EOFError

        monkeypatch.setattr("builtins.input", lambda: _raise_eof())
        assert confirm_with_user(["file.py"], "prompt text", no_confirm=False) is False


class TestRunAider:
    """run_aider makes two aider calls: a non-interactive --message-file pass
    to apply the initial prompt, then a plain interactive handoff on the same
    files. --message-file disables aider's chat mode entirely, so a single
    call can't both apply the prompt and stay interactive afterward."""

    def test_exits_when_no_files(self):
        with pytest.raises(SystemExit) as exc_info:
            run_aider([], "prompt")
        assert exc_info.value.code == 1

    @mock.patch("f_implement_issue_with_aider.subprocess.run")
    def test_applies_message_file_then_hands_off_interactively(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=0)
        written_paths = []

        real_unlink = Path.unlink

        def tracking_unlink(self, *args, **kwargs):
            written_paths.append(self)
            return real_unlink(self, *args, **kwargs)

        with mock.patch.object(Path, "unlink", tracking_unlink):
            run_aider(["file_a.py", "file_b.py"], "the prompt body")

        assert mock_run.call_count == 2
        initial_cmd, interactive_cmd = (call.args[0] for call in mock_run.call_args_list)

        assert initial_cmd[0] == "aider"
        assert initial_cmd[1:3] == ["--edit-format", "whole"]
        assert initial_cmd[3] == "--message-file"
        message_file_path = Path(initial_cmd[4])
        assert initial_cmd[5:] == ["file_a.py", "file_b.py"]

        assert interactive_cmd == [
            "aider",
            "--edit-format",
            "whole",
            "file_a.py",
            "file_b.py",
        ]

        assert written_paths == [message_file_path]
        assert not message_file_path.exists()

    @mock.patch("f_implement_issue_with_aider.subprocess.run")
    def test_propagates_nonzero_exit_code_from_initial_apply(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=3)

        with pytest.raises(SystemExit) as exc_info:
            run_aider(["file.py"], "prompt")
        assert exc_info.value.code == 3
        # A failed initial apply must not proceed to the interactive handoff.
        assert mock_run.call_count == 1

    @mock.patch("f_implement_issue_with_aider.subprocess.run")
    def test_propagates_nonzero_exit_code_from_interactive_session(self, mock_run):
        mock_run.side_effect = [mock.MagicMock(returncode=0), mock.MagicMock(returncode=5)]

        with pytest.raises(SystemExit) as exc_info:
            run_aider(["file.py"], "prompt")
        assert exc_info.value.code == 5
        assert mock_run.call_count == 2

    @mock.patch("f_implement_issue_with_aider.subprocess.run")
    def test_succeeds_silently_when_both_calls_exit_zero(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=0)
        run_aider(["file.py"], "prompt")  # should not raise
        assert mock_run.call_count == 2

    @mock.patch("f_implement_issue_with_aider.subprocess.run")
    def test_exits_when_aider_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError

        with pytest.raises(SystemExit) as exc_info:
            run_aider(["file.py"], "prompt")
        assert exc_info.value.code == 1
        assert mock_run.call_count == 1

    @mock.patch("f_implement_issue_with_aider.subprocess.run")
    def test_keyboard_interrupt_exits_cleanly(self, mock_run):
        mock_run.side_effect = KeyboardInterrupt

        with pytest.raises(SystemExit) as exc_info:
            run_aider(["file.py"], "prompt")
        assert exc_info.value.code == 0


class TestMainOrdering:
    """The issue's constraint is to fail early if Ollama isn't running, before
    any other work -- these pin that ordering against a regression."""

    @mock.patch("f_implement_issue_with_aider.load_graphify_analysis", return_value=None)
    @mock.patch("f_implement_issue_with_aider.os.chdir")
    @mock.patch("f_implement_issue_with_aider.get_repo_root", return_value="/repo/root")
    @mock.patch("f_implement_issue_with_aider.run_aider")
    @mock.patch("f_implement_issue_with_aider.resolve_files_to_edit")
    @mock.patch("f_implement_issue_with_aider.fetch_issue_from_github")
    @mock.patch("f_implement_issue_with_aider.get_repo_info")
    @mock.patch("f_implement_issue_with_aider.validate_ollama_connection")
    def test_ollama_checked_before_github_fetch(
        self,
        mock_validate,
        mock_repo_info,
        mock_fetch,
        mock_resolve,
        mock_run_aider,
        mock_get_repo_root,
        mock_chdir,
        mock_load_graphify,
    ):
        calls = []
        mock_validate.side_effect = lambda endpoint: calls.append("ollama") or True
        mock_repo_info.return_value = ("owner", "repo")
        mock_fetch.side_effect = lambda *a, **k: calls.append("github") or (
            "Title",
            "## What\nBody",
        )
        mock_resolve.return_value = ["file.py"]

        main(["-i", "42", "--no-confirm"])

        assert calls == ["ollama", "github"]
        mock_run_aider.assert_called_once()
        mock_chdir.assert_called_once_with("/repo/root")

    @mock.patch("f_implement_issue_with_aider.fetch_issue_from_github")
    @mock.patch("f_implement_issue_with_aider.get_repo_info")
    @mock.patch("f_implement_issue_with_aider.validate_ollama_connection", return_value=False)
    def test_exits_before_any_github_io_when_ollama_down(self, mock_validate, mock_repo_info, mock_fetch):
        with pytest.raises(SystemExit) as exc_info:
            main(["-i", "42"])

        assert exc_info.value.code == 1
        mock_repo_info.assert_not_called()
        mock_fetch.assert_not_called()

    @mock.patch("f_implement_issue_with_aider.os.chdir")
    @mock.patch("f_implement_issue_with_aider.get_repo_root", side_effect=ValueError("not a git repo"))
    @mock.patch("f_implement_issue_with_aider.validate_ollama_connection", return_value=True)
    def test_exits_cleanly_when_repo_root_cannot_be_determined(self, mock_validate, mock_get_repo_root, mock_chdir):
        with pytest.raises(SystemExit) as exc_info:
            main(["-i", "42"])

        assert exc_info.value.code == 1
        mock_chdir.assert_not_called()

    @mock.patch("f_implement_issue_with_aider.load_graphify_analysis", return_value=None)
    @mock.patch("f_implement_issue_with_aider.os.chdir")
    @mock.patch("f_implement_issue_with_aider.get_repo_root", return_value="/repo/root")
    @mock.patch("f_implement_issue_with_aider.run_aider")
    @mock.patch("f_implement_issue_with_aider.resolve_files_to_edit")
    @mock.patch("f_implement_issue_with_aider.get_repo_info", return_value=("owner", "repo"))
    @mock.patch("f_implement_issue_with_aider.validate_ollama_connection", return_value=True)
    def test_chdirs_to_repo_root_before_resolving_files(
        self,
        mock_validate,
        mock_repo_info,
        mock_resolve,
        mock_run_aider,
        mock_get_repo_root,
        mock_chdir,
        mock_load_graphify,
    ):
        # Regression test: paths extracted from an issue body (and the files
        # ultimately handed to aider) are resolved relative to the process
        # cwd. Without chdir'ing to the repo root first, running this script
        # from e.g. scripts/developer_tools/ makes every real repo-relative
        # path look nonexistent.
        #
        # validate_ollama_connection is mocked (not exercised elsewhere in
        # this test) purely so main() doesn't sys.exit(1) on the real
        # connectivity check before ever reaching the chdir this test is
        # actually verifying (#5810) -- environments without Ollama running
        # would otherwise fail here for an unrelated reason.
        calls = []
        mock_chdir.side_effect = lambda path: calls.append("chdir")
        mock_resolve.side_effect = lambda *a, **k: calls.append("resolve") or ["file.py"]

        main(["-f", str(Path(__file__)), "--no-confirm"])

        assert calls == ["chdir", "resolve"]
        mock_get_repo_root.assert_called_once()
