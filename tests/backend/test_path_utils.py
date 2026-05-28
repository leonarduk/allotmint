"""Tests for the safe_join path-traversal guard."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.common.path_utils import safe_join


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


def test_empty_part_returns_base(tmp_path: Path) -> None:
    # An empty string part resolves to the base itself — allowed
    result = safe_join(tmp_path, "")
    assert result == tmp_path.resolve()


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
