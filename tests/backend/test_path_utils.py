"""Tests for path_utils: safe_join path-traversal guard and sanitize_for_log."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.common.path_utils import safe_join, sanitize_for_log


def test_valid_single_part(tmp_path: Path) -> None:
    result = safe_join(tmp_path, "alice")
    assert result == tmp_path / "alice"


def test_valid_multi_part(tmp_path: Path) -> None:
    result = safe_join(tmp_path, "alice", "isa.json")
    assert result == tmp_path / "alice" / "isa.json"


def test_traversal_dotdot_blocked(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="traversal"):
        safe_join(tmp_path, "../etc/passwd")


def test_traversal_nested_dotdot_blocked(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="traversal"):
        safe_join(tmp_path, "alice", "../../etc/shadow")


def test_traversal_absolute_blocked(tmp_path: Path) -> None:
    # An absolute path as a part should escape the base
    with pytest.raises(ValueError, match="traversal"):
        safe_join(tmp_path, "/etc/passwd")


def test_empty_part_raises(tmp_path: Path) -> None:
    # An empty string resolves to the base itself, which is rejected
    with pytest.raises(ValueError, match="traversal"):
        safe_join(tmp_path, "")


def test_dot_part_raises(tmp_path: Path) -> None:
    # "." also resolves to the base and must be rejected
    with pytest.raises(ValueError, match="traversal"):
        safe_join(tmp_path, ".")


def test_literal_filename_with_dots(tmp_path: Path) -> None:
    # Filenames that contain dots but are not traversal are fine
    result = safe_join(tmp_path, "file.v2.json")
    assert result == tmp_path / "file.v2.json"


def test_deeply_nested_valid_path(tmp_path: Path) -> None:
    result = safe_join(tmp_path, "owner", "subdir", "file.json")
    assert result == tmp_path / "owner" / "subdir" / "file.json"


def test_returns_path_object(tmp_path: Path) -> None:
    result = safe_join(tmp_path, "x")
    assert isinstance(result, Path)


def test_sanitize_for_log_strips_control_chars() -> None:
    dirty = "hello" + chr(0) + "world" + chr(10) + "foo" + chr(31)
    assert sanitize_for_log(dirty) == "helloworldfoo"


def test_sanitize_for_log_keeps_printable() -> None:
    assert sanitize_for_log("alice/isa.json") == "alice/isa.json"


def test_sanitize_for_log_non_string() -> None:
    assert sanitize_for_log(42) == "42"


def test_sanitize_for_log_strips_del() -> None:
    assert sanitize_for_log("ab" + chr(127) + "cd") == "abcd"


def test_null_byte_in_part_safe(tmp_path: Path) -> None:
    # Null bytes in a path component must not escape the base directory.
    # On POSIX, os.path.realpath raises ValueError for embedded null bytes.
    # On Windows, the null byte truncates the path — still safe.
    try:
        result = safe_join(tmp_path, "alice" + chr(0) + "../../etc/passwd")
        # If no exception, the resolved path must remain inside base
        assert str(result).startswith(str(tmp_path))
    except ValueError:
        pass  # POSIX: null byte in path raises before the traversal check


@pytest.mark.skipif(
    not hasattr(__import__("os"), "symlink"),
    reason="symlinks not supported on this platform",
)
def test_symlink_traversal_blocked(tmp_path: Path) -> None:
    import os

    outside = tmp_path.parent / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    os.symlink(outside, link)
    # link resolves to outside tmp_path — must be rejected
    with pytest.raises(ValueError, match="traversal"):
        safe_join(tmp_path, "link")
