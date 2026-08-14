"""Tests confirming LocalDataProvider rejects path traversal in owner/account inputs."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.common.data_providers import (
    LocalDataProvider,
    MissingData,
    S3DataProvider,
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


# ---------------------------------------------------------------------------
# S3DataProvider._client — thread-safe caching
# ---------------------------------------------------------------------------


@pytest.fixture()
def s3_provider(monkeypatch: pytest.MonkeyPatch) -> S3DataProvider:
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    return S3DataProvider()


def test_client_returns_cached_instance_on_subsequent_calls(s3_provider: S3DataProvider) -> None:
    with patch("boto3.client") as mock_boto_client:
        mock_boto_client.return_value = object()
        first = s3_provider._client()
        second = s3_provider._client()
    assert first is second
    mock_boto_client.assert_called_once_with("s3")


def test_client_creation_is_thread_safe_under_concurrent_calls(s3_provider: S3DataProvider) -> None:
    created_clients = []

    def _slow_client(*_args, **_kwargs):
        # Simulate the latency of real client construction so concurrent
        # threads are likely to race inside _client() without the lock.
        threading.Event().wait(0.01)
        client = object()
        created_clients.append(client)
        return client

    with patch("boto3.client", side_effect=_slow_client) as mock_boto_client:
        results: list[object] = [None] * 20  # type: ignore[list-item]

        def _call(index: int) -> None:
            results[index] = s3_provider._client()

        threads = [threading.Thread(target=_call, args=(i,)) for i in range(len(results))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert mock_boto_client.call_count == 1
    assert len(created_clients) == 1
    assert all(result is created_clients[0] for result in results)
