"""Tests for scripts/dev_tools/comment_formats.py."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "dev_tools"))

from comment_formats import to_fixer, to_jsonl


def test_to_jsonl_preserves_all_fields():
    """JSONL format includes all comment fields unchanged."""
    comments = [
        {
            "id": 123,
            "type": "inline",
            "path": "app.py",
            "line": 42,
            "body": "Fix this.",
            "author": "user",
            "created_at": "2026-06-18T17:00:00Z",
        }
    ]
    result = list(to_jsonl(comments))
    assert len(result) == 1

    parsed = json.loads(result[0])
    assert parsed["id"] == 123
    assert parsed["type"] == "inline"
    assert parsed["path"] == "app.py"
    assert parsed["line"] == 42
    assert parsed["body"] == "Fix this."
    assert parsed["created_at"] == "2026-06-18T17:00:00Z"


def test_to_jsonl_multi_line():
    """JSONL handles multi-line bodies as single JSON values."""
    comments = [
        {
            "id": 1,
            "type": "top-level",
            "body": "Line 1\nLine 2\nLine 3",
            "author": "user",
            "created_at": "2026-06-18T17:00:00Z",
        }
    ]
    result = list(to_jsonl(comments))
    parsed = json.loads(result[0])
    assert parsed["body"] == "Line 1\nLine 2\nLine 3"


def test_to_fixer_inline_with_path_and_line():
    """Inline comment with path and line uses path:line format."""
    comments = [
        {
            "type": "inline",
            "path": "backend/app.py",
            "line": 42,
            "body": "Use bucket.arn_for_objects() instead.",
        }
    ]
    result = list(to_fixer(comments))
    assert result[0] == "backend/app.py:42 — Use bucket.arn_for_objects() instead."


def test_to_fixer_inline_missing_path_falls_back_to_general():
    """Inline comment without path falls back to (general) format."""
    comments = [
        {
            "type": "inline",
            "path": None,
            "line": 42,
            "body": "Comment without path.",
        }
    ]
    result = list(to_fixer(comments))
    assert result[0] == "(general) — Comment without path."


def test_to_fixer_inline_missing_line_falls_back_to_general():
    """Inline comment without line falls back to (general) format."""
    comments = [
        {
            "type": "inline",
            "path": "app.py",
            "line": None,
            "body": "Comment without line.",
        }
    ]
    result = list(to_fixer(comments))
    assert result[0] == "(general) — Comment without line."


def test_to_fixer_top_level():
    """Top-level comment uses (general) format."""
    comments = [
        {
            "type": "top-level",
            "body": "Split this function — exceeds 60 lines.",
        }
    ]
    result = list(to_fixer(comments))
    assert result[0] == "(general) — Split this function — exceeds 60 lines."


def test_to_fixer_unknown_type():
    """Unknown comment type falls back to (unknown-type) format."""
    comments = [
        {
            "type": "pending",
            "body": "Awaiting review.",
        }
    ]
    result = list(to_fixer(comments))
    assert result[0] == "(pending) — Awaiting review."


def test_to_fixer_multiline_body_indentation():
    """Multi-line bodies are indented for readability."""
    comments = [
        {
            "type": "top-level",
            "body": "Line 1\nLine 2\nLine 3",
        }
    ]
    result = list(to_fixer(comments))
    assert result == [
        "(general) — Line 1",
        "  Line 2",
        "  Line 3",
    ]


def test_to_fixer_inline_multiline_body():
    """Inline comment with multi-line body is indented."""
    comments = [
        {
            "type": "inline",
            "path": "file.py",
            "line": 10,
            "body": "Error:\nLine 2\nLine 3",
        }
    ]
    result = list(to_fixer(comments))
    assert result == [
        "file.py:10 — Error:",
        "  Line 2",
        "  Line 3",
    ]


def test_to_fixer_preserves_body_verbatim():
    """Body content is preserved exactly, including whitespace."""
    body_with_spaces = "  indented code block  "
    comments = [
        {
            "type": "top-level",
            "body": body_with_spaces,
        }
    ]
    result = list(to_fixer(comments))
    assert body_with_spaces in result[0]


def test_to_fixer_omits_id_and_created_at():
    """Fixer format does not include id or created_at."""
    comments = [
        {
            "type": "inline",
            "path": "app.py",
            "line": 5,
            "body": "Comment",
            "id": 999,
            "created_at": "2026-06-18T17:00:00Z",
            "author": "user",
        }
    ]
    result = list(to_fixer(comments))
    output = "\n".join(result)
    assert "999" not in output
    assert "2026-06-18T17:00:00Z" not in output
    assert "id" not in output
    assert "created_at" not in output


def test_to_fixer_empty_body():
    """Comment with empty body still produces output."""
    comments = [
        {
            "type": "top-level",
            "body": "",
        }
    ]
    result = list(to_fixer(comments))
    assert result == ["(general) — "]


def test_to_jsonl_format_exact_output():
    """JSONL output matches expected JSON format for regression testing."""
    comments = [
        {
            "id": 1,
            "author": "bot",
            "type": "top-level",
            "body": "Test",
            "created_at": "2026-06-18T17:00:00Z",
        }
    ]
    result = list(to_jsonl(comments))
    expected = json.dumps(comments[0])
    assert result[0] == expected
