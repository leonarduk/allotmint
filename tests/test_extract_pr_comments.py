"""Tests for scripts/dev_tools/extract_pr_comments.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "dev_tools"))

from extract_pr_comments import format_inline_comment, format_top_level_comment


def test_format_inline_comment_with_none_user():
    """A None 'user' field (deleted account) does not crash formatting."""
    comment = {
        "id": 1,
        "user": None,
        "path": "app.py",
        "line": 10,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "Fix this.",
    }
    result = format_inline_comment(comment, {})
    assert result["author"] is None


def test_format_inline_comment_with_missing_user_key():
    """A missing 'user' key still resolves to a None author."""
    comment = {
        "id": 2,
        "path": "app.py",
        "line": 10,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "Fix this.",
    }
    result = format_inline_comment(comment, {})
    assert result["author"] is None


def test_format_top_level_comment_with_none_user():
    """A None 'user' field (deleted account) does not crash formatting."""
    comment = {
        "id": 3,
        "user": None,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "LGTM.",
    }
    result = format_top_level_comment(comment)
    assert result["author"] is None


def test_format_top_level_comment_with_missing_user_key():
    """A missing 'user' key still resolves to a None author."""
    comment = {
        "id": 4,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "LGTM.",
    }
    result = format_top_level_comment(comment)
    assert result["author"] is None


def test_format_inline_comment_with_valid_user():
    """A valid 'user' dict still extracts the login."""
    comment = {
        "id": 5,
        "user": {"login": "octocat"},
        "path": "app.py",
        "line": 10,
        "created_at": "2026-06-18T17:00:00Z",
        "body": "Fix this.",
    }
    result = format_inline_comment(comment, {})
    assert result["author"] == "octocat"
