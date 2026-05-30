"""Tests confirming LocalDataProvider rejects path traversal in owner/account inputs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.common.data_providers import (
    InvalidPayload,
    LocalDataProvider,
    MissingData,
)


@pytest.fixture()
def provider() -> LocalDataProvider:
    return LocalDataProvider()


@pytest.fixture()
def accounts_root(tmp_path: Path) -> Path:
    root = tmp_path / "accounts"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# load_account — happy path
# ---------------------------------------------------------------------------


def test_load_account_valid(accounts_root: Path, provider: LocalDataProvider) -> None:
    owner_dir = accounts_root / "alice"
    owner_dir.mkdir()
    (owner_dir / "isa.json").write_text(json.dumps({"holdings": []}))
    obj = provider.load_account("alice", "isa", accounts_root)
    assert obj.owner == "alice"
    assert obj.account == "isa"
    assert obj.data == {"holdings": []}


# ---------------------------------------------------------------------------
# load_account — path traversal
# ---------------------------------------------------------------------------


def test_load_account_dotdot_owner_blocked(accounts_root: Path, provider: LocalDataProvider) -> None:
    with pytest.raises(MissingData):
        provider.load_account("../evil", "isa", accounts_root)


def test_load_account_dotdot_account_blocked(accounts_root: Path, provider: LocalDataProvider) -> None:
    owner_dir = accounts_root / "alice"
    owner_dir.mkdir()
    with pytest.raises(MissingData):
        provider.load_account("alice", "../../etc/passwd", accounts_root)


def test_load_account_absolute_owner_blocked(accounts_root: Path, provider: LocalDataProvider) -> None:
    with pytest.raises(MissingData):
        provider.load_account("/etc/passwd", "isa", accounts_root)


def test_load_account_percent_encoded_owner_blocked(accounts_root: Path, provider: LocalDataProvider) -> None:
    # Percent-encoding is URL-layer; at this layer the literal string is still blocked
    # because it resolves to a safe path (no actual slash), but we confirm no panic.
    # On most OS a literal '%2F' in a file name is valid — verify no traversal occurs.
    result_or_missing = None
    try:
        result_or_missing = provider.load_account("..%2Fevil", "isa", accounts_root)
    except MissingData:
        pass  # expected: file does not exist
    except ValueError:
        pass  # safe_join may also raise ValueError
    if result_or_missing is not None:
        # If it didn't raise, the resolved path must still be inside accounts_root.
        assert str(accounts_root) in str(result_or_missing)


# ---------------------------------------------------------------------------
# load_person_meta — path traversal
# ---------------------------------------------------------------------------


def test_load_person_meta_dotdot_blocked(accounts_root: Path, provider: LocalDataProvider) -> None:
    with pytest.raises(MissingData):
        provider.load_person_meta("../evil", accounts_root)


def test_load_person_meta_valid_missing_file(accounts_root: Path, provider: LocalDataProvider) -> None:
    # Owner dir exists but no person.json → MissingData (not a security error)
    owner_dir = accounts_root / "bob"
    owner_dir.mkdir()
    with pytest.raises(MissingData):
        provider.load_person_meta("bob", accounts_root)


def test_load_person_meta_valid(accounts_root: Path, provider: LocalDataProvider) -> None:
    owner_dir = accounts_root / "carol"
    owner_dir.mkdir()
    (owner_dir / "person.json").write_text(json.dumps({"full_name": "Carol"}))
    obj = provider.load_person_meta("carol", accounts_root)
    assert obj.owner == "carol"
    assert obj.metadata.get("full_name") == "Carol"
