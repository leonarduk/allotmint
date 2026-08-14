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
    spec = importlib.util.spec_from_file_location("extract_pr_comments_test", SCRIPTS_DIR / "extract_pr_comments.py")
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
    """A valid 'user' dict still extracts the login, and path/line are propagated (#5322)."""
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
    assert result["path"] == "app.py"
    assert result["line"] == 10


def test_format_top_level_comment_with_valid_user(mod):
    """format_top_level_comment's full output shape for a normal comment (#5322).

    The existing None-user/missing-user tests only cover the author field;
    nothing previously asserted the full mapping (id, type, created_at, body)
    for the ordinary case, unlike format_inline_comment's valid-user test.
    """
    comment = {
        "id": 6,
        "user": {"login": "octocat"},
        "created_at": "2026-06-18T17:00:00Z",
        "body": "LGTM.",
    }
    result = mod.format_top_level_comment(comment)
    assert result == {
        "id": 6,
        "author": "octocat",
        "type": "top-level",
        "created_at": "2026-06-18T17:00:00Z",
        "body": "LGTM.",
    }


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


# --- fetch_paginated(strict=True) tests ---


def test_fetch_paginated_strict_first_page_failure_raises(mod):
    """strict=True raises FetchPaginatedError when the very first page fails."""
    with patch.object(mod, "run_gh_command", return_value=("", 1)):
        with pytest.raises(mod.FetchPaginatedError, match="failed"):
            mod.fetch_paginated("owner", "repo", "/some/endpoint", strict=True)


def test_fetch_paginated_strict_partial_failure_raises_after_collecting_items(mod):
    """strict=True raises even after some items were already collected."""
    responses = [
        (json.dumps([{"id": 1}]), 0),
        ("", 1),
    ]
    with patch.object(mod, "run_gh_command", side_effect=responses):
        with pytest.raises(mod.FetchPaginatedError, match="collecting 1 items"):
            mod.fetch_paginated("owner", "repo", "/some/endpoint", strict=True)


def test_fetch_paginated_strict_invalid_json_raises(mod):
    """strict=True raises FetchPaginatedError on a JSON parse failure."""
    responses = [
        (json.dumps([{"id": 1}]), 0),
        ("not json", 0),
    ]
    with patch.object(mod, "run_gh_command", side_effect=responses):
        with pytest.raises(mod.FetchPaginatedError, match="Failed to parse JSON"):
            mod.fetch_paginated("owner", "repo", "/some/endpoint", strict=True)


def test_fetch_paginated_strict_exhausts_multiple_pages_before_failing(mod):
    """strict=True still raises after several successful pages precede the failure,
    i.e. the retry/page cap does not swallow an eventual failure."""
    responses = [
        (json.dumps([{"id": 1}]), 0),
        (json.dumps([{"id": 2}]), 0),
        (json.dumps([{"id": 3}]), 0),
        ("", 1),
    ]
    with patch.object(mod, "run_gh_command", side_effect=responses):
        with pytest.raises(mod.FetchPaginatedError, match="collecting 3 items"):
            mod.fetch_paginated("owner", "repo", "/some/endpoint", strict=True)


def test_fetch_paginated_strict_success_returns_items_untruncated(mod):
    """strict=True does not affect the success path: items are returned normally."""
    pages = [
        json.dumps([{"id": 1}, {"id": 2}]),
        json.dumps([]),
    ]
    with patch.object(mod, "run_gh_command", side_effect=[(p, 0) for p in pages]):
        items, truncated = mod.fetch_paginated("owner", "repo", "/some/endpoint", strict=True)

    assert items == [{"id": 1}, {"id": 2}]
    assert truncated is False


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


def test_process_comments_deduplicates_by_id(mod):
    """Two comments sharing an id must collapse to one, keeping the first-seen (#5322).

    Nothing previously exercised process_comments' own dedup-by-id step
    directly -- the existing truncation test only passes empty comment lists.
    """
    since = mod.parse_iso_datetime("2020-01-01T00:00:00Z")
    duplicate_inline = [
        {
            "id": 42,
            "user": {"login": "octocat"},
            "path": "app.py",
            "line": 1,
            "created_at": "2026-06-18T17:00:00Z",
            "body": "first",
        },
        {
            "id": 42,
            "user": {"login": "octocat"},
            "path": "app.py",
            "line": 1,
            "created_at": "2026-06-18T17:00:01Z",
            "body": "duplicate, should be dropped",
        },
    ]
    with (
        patch.object(mod, "fetch_reviews", return_value=({}, False)),
        patch.object(mod, "fetch_inline_comments", return_value=(duplicate_inline, False)),
        patch.object(mod, "fetch_top_level_comments", return_value=([], False)),
    ):
        comments, truncated = mod.process_comments("owner", "repo", 1, since, False)

    assert len(comments) == 1
    assert comments[0]["body"] == "first"
    assert truncated is False
