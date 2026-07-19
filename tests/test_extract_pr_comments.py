from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "build_tools"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_extract_pr_comments():
    spec = importlib.util.spec_from_file_location(
        "extract_pr_comments_test", SCRIPTS_DIR / "extract_pr_comments.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return load_extract_pr_comments()


# --- format_inline_comment() / format_top_level_comment() None-user tests ---


def test_format_inline_comment_with_none_user(mod):
    """A None 'user' field (deleted account) does not crash formatting."""
    comment = {
        "id": 1,
        "user": None,
        "path": "app.py",
        "line": 10,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "Fix this.",
    }
    result = mod.format_inline_comment(comment, {})
    assert result["author"] is None


def test_format_inline_comment_with_missing_user_key(mod):
    """A missing 'user' key still resolves to a None author."""
    comment = {
        "id": 2,
        "path": "app.py",
        "line": 10,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "Fix this.",
    }
    result = mod.format_inline_comment(comment, {})
    assert result["author"] is None


def test_format_top_level_comment_with_none_user(mod):
    """A None 'user' field (deleted account) does not crash formatting."""
    comment = {
        "id": 3,
        "user": None,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "LGTM.",
    }
    result = mod.format_top_level_comment(comment)
    assert result["author"] is None


def test_format_top_level_comment_with_missing_user_key(mod):
    """A missing 'user' key still resolves to a None author."""
    comment = {
        "id": 4,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "LGTM.",
    }
    result = mod.format_top_level_comment(comment)
    assert result["author"] is None


def test_format_inline_comment_with_valid_user(mod):
    """A valid 'user' dict still extracts the login."""
    comment = {
        "id": 5,
        "user": {"login": "octocat"},
        "path": "app.py",
        "line": 10,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "Fix this.",
    }
    result = mod.format_inline_comment(comment, {})
    assert result["author"] == "octocat"


# --- fetch_paginated() truncation tests ---


def test_fetch_paginated_all_pages_succeed(mod):
    pages = [
        json.dumps([{"id": 1}, {"id": 2}]),
        json.dumps([]),
    ]
    with patch.object(mod, "run_gh_command", side_effect=[(p, 0) for p in pages]):
        items, truncated = mod.fetch_paginated("owner", "repo", "/some/endpoint")

    assert items == [{"id": 1}, {"id": 2}]
    assert truncated is False


def test_fetch_paginated_partial_failure_returns_truncated(mod):
    responses = [
        (json.dumps([{"id": 1}]), 0),
        ("", 1),
    ]
    with patch.object(mod, "run_gh_command", side_effect=responses):
        items, truncated = mod.fetch_paginated("owner", "repo", "/some/endpoint")

    assert items == [{"id": 1}]
    assert truncated is True


def test_fetch_paginated_first_page_failure_returns_truncated(mod):
    with patch.object(mod, "run_gh_command", return_value=("", 1)):
        items, truncated = mod.fetch_paginated("owner", "repo", "/some/endpoint")

    assert items == []
    assert truncated is True


def test_fetch_paginated_invalid_json_returns_truncated(mod):
    responses = [
        (json.dumps([{"id": 1}]), 0),
        ("not json", 0),
    ]
    with patch.object(mod, "run_gh_command", side_effect=responses):
        items, truncated = mod.fetch_paginated("owner", "repo", "/some/endpoint")

    assert items == [{"id": 1}]
    assert truncated is True


# --- write_output() truncated-flag placement tests ---


def test_write_output_jsonl_no_truncation_unchanged(mod, capsys):
    comments = [{"id": 1, "body": "hi"}]
    mod.write_output(comments, None, "jsonl", truncated=False)
    out = capsys.readouterr().out.strip().splitlines()

    assert out == [json.dumps({"id": 1, "body": "hi"})]


def test_write_output_jsonl_truncated_appends_last_line(mod, capsys):
    comments = [{"id": 1, "body": "hi"}]
    mod.write_output(comments, None, "jsonl", truncated=True)
    out = capsys.readouterr().out.strip().splitlines()

    assert out[-1] == json.dumps({"truncated": True})
    assert out[0] == json.dumps({"id": 1, "body": "hi"})


def test_write_output_fixer_format_ignores_truncated(mod, capsys):
    comments = [{"id": 1, "type": "top-level", "body": "hi"}]
    mod.write_output(comments, None, "fixer", truncated=True)
    out = capsys.readouterr().out

    assert "truncated" not in out


# --- process_comments() propagation test ---


def test_process_comments_propagates_truncated(mod):
    with (
        patch.object(mod, "fetch_reviews", return_value=({}, False)),
        patch.object(mod, "fetch_inline_comments", return_value=([], True)),
        patch.object(mod, "fetch_top_level_comments", return_value=([], False)),
    ):
        comments, truncated = mod.process_comments(
            "owner", "repo", 1, mod.parse_iso_datetime("2020-01-01T00:00:00Z"), False
        )

    assert comments == []
    assert truncated is True
