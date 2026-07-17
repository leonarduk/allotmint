"""Unit tests for scripts/check_account_slug_collisions.py."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from unittest import mock

import boto3
from botocore.stub import Stubber

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_account_slug_collisions.py"
spec = importlib.util.spec_from_file_location("check_account_slug_collisions", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(_mod)  # type: ignore[union-attr]
find_collisions = _mod.find_collisions
local_slugs = _mod.local_slugs
remote_slugs = _mod.remote_slugs
main = _mod.main

BUCKET = "test-data-bucket"
PREFIX = "accounts/"


def _make_local_account(accounts_dir: Path, slug: str, email: str) -> None:
    owner_dir = accounts_dir / slug
    owner_dir.mkdir(parents=True)
    (owner_dir / "person.json").write_text(json.dumps({"email": email}))


def _body(data: dict) -> io.BytesIO:
    return io.BytesIO(json.dumps(data).encode("utf-8"))


def _stubbed_client(list_prefixes: list[str], get_object_by_key: dict[str, dict | None]):
    """Build an S3 client stubbed with one list_objects_v2 call and one
    get_object call per key in `get_object_by_key` (a None value stubs a
    NoSuchKey error, matching a missing remote person.json)."""
    client = boto3.client("s3", region_name="us-east-1")
    stubber = Stubber(client)
    stubber.add_response(
        "list_objects_v2",
        {"CommonPrefixes": [{"Prefix": prefix} for prefix in list_prefixes]},
    )
    for key, body_dict in get_object_by_key.items():
        if body_dict is None:
            stubber.add_client_error(
                "get_object",
                service_error_code="NoSuchKey",
                expected_params={"Bucket": BUCKET, "Key": key},
            )
        else:
            stubber.add_response("get_object", {"Body": _body(body_dict)}, {"Bucket": BUCKET, "Key": key})
    stubber.activate()
    return client


def test_local_slugs_lists_subdirectories(tmp_path) -> None:
    accounts_dir = tmp_path / "accounts"
    _make_local_account(accounts_dir, "alice", "alice@example.com")
    _make_local_account(accounts_dir, "bob", "bob@example.com")
    (accounts_dir / "not-a-dir.txt").write_text("noise")

    assert local_slugs(accounts_dir) == ["alice", "bob"]


def test_local_slugs_missing_directory_returns_empty(tmp_path) -> None:
    assert local_slugs(tmp_path / "nope") == []


def test_remote_slugs_parses_common_prefixes() -> None:
    client = _stubbed_client(["accounts/alice/", "accounts/bob/"], {})
    assert remote_slugs(client, BUCKET, PREFIX) == {"alice", "bob"}


def test_new_local_slug_is_not_a_collision(tmp_path) -> None:
    accounts_dir = tmp_path / "accounts"
    _make_local_account(accounts_dir, "carol", "carol@example.com")
    client = _stubbed_client(["accounts/alice/"], {})

    assert find_collisions(accounts_dir, client, BUCKET, PREFIX) == []


def test_same_owner_reslug_is_not_a_collision(tmp_path) -> None:
    accounts_dir = tmp_path / "accounts"
    _make_local_account(accounts_dir, "alice", "alice@example.com")
    client = _stubbed_client(
        ["accounts/alice/"],
        {"accounts/alice/person.json": {"email": "alice@example.com"}},
    )

    assert find_collisions(accounts_dir, client, BUCKET, PREFIX) == []


def test_different_owner_same_slug_is_a_collision(tmp_path) -> None:
    accounts_dir = tmp_path / "accounts"
    _make_local_account(accounts_dir, "alice", "new-alice@example.com")
    client = _stubbed_client(
        ["accounts/alice/"],
        {"accounts/alice/person.json": {"email": "old-alice@example.com"}},
    )

    collisions = find_collisions(accounts_dir, client, BUCKET, PREFIX)
    assert len(collisions) == 1
    assert collisions[0].slug == "alice"
    assert "new-alice@example.com" in str(collisions[0])
    assert "old-alice@example.com" in str(collisions[0])


def test_missing_remote_person_json_is_not_treated_as_collision(tmp_path) -> None:
    accounts_dir = tmp_path / "accounts"
    _make_local_account(accounts_dir, "alice", "alice@example.com")
    client = _stubbed_client(["accounts/alice/"], {"accounts/alice/person.json": None})

    assert find_collisions(accounts_dir, client, BUCKET, PREFIX) == []


def test_missing_local_person_json_is_not_treated_as_collision(tmp_path) -> None:
    accounts_dir = tmp_path / "accounts"
    (accounts_dir / "alice").mkdir(parents=True)
    client = _stubbed_client(
        ["accounts/alice/"],
        {"accounts/alice/person.json": {"email": "old-alice@example.com"}},
    )

    assert find_collisions(accounts_dir, client, BUCKET, PREFIX) == []


def test_main_forwards_region_and_profile_to_boto_session(tmp_path) -> None:
    with (
        mock.patch.object(_mod, "boto3") as mock_boto3,
        mock.patch.object(_mod, "find_collisions", return_value=[]),
    ):
        argv = [
            "check_account_slug_collisions.py",
            "--bucket",
            BUCKET,
            "--accounts-dir",
            str(tmp_path),
            "--region",
            "eu-west-2",
            "--profile",
            "deployer",
        ]

        exit_code = main(argv)

        assert exit_code == 0
        mock_boto3.Session.assert_called_once_with(profile_name="deployer", region_name="eu-west-2")


def test_main_defaults_region_and_profile_to_none(tmp_path) -> None:
    with (
        mock.patch.object(_mod, "boto3") as mock_boto3,
        mock.patch.object(_mod, "find_collisions", return_value=[]),
    ):
        argv = ["check_account_slug_collisions.py", "--bucket", BUCKET, "--accounts-dir", str(tmp_path)]

        main(argv)

        mock_boto3.Session.assert_called_once_with(profile_name=None, region_name=None)
