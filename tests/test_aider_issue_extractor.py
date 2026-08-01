"""Unit tests for the aider issue extractor script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "developer_tools"))

from f_aider_issue_extractor import (  # noqa: E402
    confirm_with_user,
    extract_file_paths_from_issue,
    fetch_issue_from_github,
    formulate_aider_prompt,
    load_issue_from_file,
    parse_issue_body,
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


class TestExtractFilePathsFromIssue:
    def test_finds_existing_file_path(self):
        real_file = "scripts/developer_tools/f_aider_issue_extractor.py"
        body = f"See {real_file} for details."
        paths = extract_file_paths_from_issue(body)
        assert real_file in paths

    def test_ignores_paths_that_do_not_exist(self):
        body = "See totally/made/up/path.py for details."
        assert extract_file_paths_from_issue(body) == []

    def test_returns_empty_list_when_no_paths_mentioned(self):
        assert extract_file_paths_from_issue("No files mentioned here.") == []


class TestFormulateAiderPrompt:
    def test_includes_title_and_sections(self):
        sections = {"what": "Do the thing.", "why": "Because it matters."}
        prompt = formulate_aider_prompt("Issue Title", sections)
        assert prompt.startswith("Issue Title")
        assert "What:" in prompt
        assert "Do the thing." in prompt
        assert "Why:" in prompt

    def test_omits_missing_sections(self):
        prompt = formulate_aider_prompt("Issue Title", {"what": "Only this."})
        assert "Why:" not in prompt
        assert "How:" not in prompt

    def test_skips_blank_sections(self):
        prompt = formulate_aider_prompt("Issue Title", {"what": "   "})
        assert "What:" not in prompt


class TestFetchIssueFromGithub:
    @mock.patch("f_aider_issue_extractor.requests.get")
    def test_returns_title_and_body_on_success(self, mock_get):
        mock_response = mock.MagicMock()
        mock_response.json.return_value = {"title": "Bug title", "body": "Bug body"}
        mock_get.return_value = mock_response

        title, body = fetch_issue_from_github("owner", "repo", 42)
        assert title == "Bug title"
        assert body == "Bug body"

    @mock.patch("f_aider_issue_extractor.requests.get")
    def test_exits_when_issue_has_no_title(self, mock_get):
        mock_response = mock.MagicMock()
        mock_response.json.return_value = {"title": "", "body": "Bug body"}
        mock_get.return_value = mock_response

        with pytest.raises(SystemExit) as exc_info:
            fetch_issue_from_github("owner", "repo", 42)
        assert exc_info.value.code == 1

    @mock.patch("f_aider_issue_extractor.requests.get")
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
    @mock.patch("f_aider_issue_extractor.fetch_ollama_review")
    def test_parses_json_array_from_response(self, mock_fetch):
        real_file = "scripts/developer_tools/f_aider_issue_extractor.py"
        mock_fetch.return_value = f'Here you go: ["{real_file}"]'

        result = suggest_files_with_ollama("title", "body", [], "http://x", "model")
        assert result == [real_file]

    @mock.patch("f_aider_issue_extractor.fetch_ollama_review")
    def test_falls_back_to_extracted_paths_when_ollama_fails(self, mock_fetch):
        mock_fetch.side_effect = SystemExit(1)

        result = suggest_files_with_ollama("title", "body", ["existing.py"], "http://x", "model")
        assert result == ["existing.py"]

    @mock.patch("f_aider_issue_extractor.fetch_ollama_review")
    def test_falls_back_when_response_has_no_json(self, mock_fetch):
        mock_fetch.return_value = "no json here"

        result = suggest_files_with_ollama("title", "body", ["existing.py"], "http://x", "model")
        assert result == ["existing.py"]


class TestConfirmWithUser:
    def test_no_confirm_flag_skips_prompt(self, capsys):
        assert confirm_with_user(["file.py"], "prompt text", no_confirm=True) is True

    def test_eof_on_input_is_treated_as_declined(self, monkeypatch):
        def _raise_eof():
            raise EOFError

        monkeypatch.setattr("builtins.input", lambda: _raise_eof())
        assert confirm_with_user(["file.py"], "prompt text", no_confirm=False) is False
