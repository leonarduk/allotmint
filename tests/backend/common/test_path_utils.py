import pytest

from backend.common.path_utils import safe_join


def test_simple_join(tmp_path):
    result = safe_join(tmp_path, "alice")
    assert result == tmp_path / "alice"


def test_nested_join(tmp_path):
    result = safe_join(tmp_path, "alice", "ISA")
    assert result == tmp_path / "alice" / "ISA"


def test_blocks_double_dot_traversal(tmp_path):
    with pytest.raises(ValueError, match="Path traversal"):
        safe_join(tmp_path, "..", "etc", "passwd")


def test_blocks_absolute_part(tmp_path):
    with pytest.raises(ValueError, match="Path traversal"):
        safe_join(tmp_path, "/etc/passwd")


def test_blocks_encoded_traversal(tmp_path):
    with pytest.raises(ValueError, match="Path traversal"):
        safe_join(tmp_path, "alice", "..", "..", "etc")


def test_base_does_not_need_to_exist(tmp_path):
    new_owner = tmp_path / "new_owner"
    assert not new_owner.exists()
    result = safe_join(new_owner, "ISA")
    assert result == new_owner / "ISA"


def test_returns_path_object(tmp_path):
    from pathlib import Path

    result = safe_join(tmp_path, "alice")
    assert isinstance(result, Path)


def test_exact_base_allowed(tmp_path):
    result = safe_join(tmp_path)
    assert result == tmp_path.resolve()
