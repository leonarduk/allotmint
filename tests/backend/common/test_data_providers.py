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
    # '..%2Fevil' is not a real path traversal — '%2F' is three literal characters at the
    # filesystem layer, not a slash (URL-decoding happens in the HTTP layer above this).
    # safe_join does not reject it as traversal, so the call proceeds and fails with
    # MissingData because the directory does not exist.  The key property we verify is
    # that no file outside accounts_root is read (confirmed by MissingData, not IOError).
    with pytest.raises(MissingData):
        provider.load_account("..%2Fevil", "isa", accounts_root)


# ---------------------------------------------------------------------------
# load_person_meta — path traversal
# ---------------------------------------------------------------------------


def test_load_person_meta_dotdot_blocked(accounts_root: Path, provider: LocalDataProvider) -> None:
    with pytest.raises(MissingData):
        provider.load_person_meta("../evil", accounts_root)


def test_load_person_meta_absolute_path_blocked(accounts_root: Path, provider: LocalDataProvider) -> None:
    """An absolute path as owner is rejected by safe_join."""
    with pytest.raises(MissingData):
        provider.load_person_meta("/etc/passwd", accounts_root)


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
