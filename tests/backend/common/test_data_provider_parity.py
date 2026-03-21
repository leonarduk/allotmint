import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.common.data_loader as data_loader
from backend.config import Config

# Intentional known difference:
# - Local discovery normalises canonical account names such as ISA/GIA/SIPP to
#   lowercase, while the AWS implementation preserves the casing from object
#   keys. These parity tests therefore compare a normalised lowercase view of
#   owner and account identifiers so they only fail on behavioural drift.


class MockS3Client:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects

    def list_objects_v2(self, **kwargs):
        prefix = kwargs["Prefix"]
        keys = sorted(key for key in self._objects if key.startswith(prefix))
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}

    def get_object(self, Bucket, Key):  # noqa: N803 - boto3 compatibility
        if Key not in self._objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self._objects[Key])}


@pytest.fixture
def shared_provider_dataset(tmp_path: Path) -> dict[str, object]:
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir(parents=True, exist_ok=True)

    owners = {
        "Alice": {
            "person": {
                "full_name": "Alice Example",
                "email": "alice@example.com",
                "viewers": ["bob@example.com"],
                "dob": "1980-01-01",
            },
            "accounts": {
                "ISA": {"balance": 101, "holdings": [{"ticker": "VWRP", "units": 2}]},
                "GIA": {"balance": 55, "cash": 12},
            },
        },
        "bob": {
            "person": {
                "full_name": "Bob Example",
                "email": "bob@example.com",
                "viewers": [],
                "dob": "1985-05-05",
            },
            "accounts": {
                "SIPP": {"balance": 205},
            },
        },
    }

    for owner, payload in owners.items():
        owner_dir = accounts_root / owner
        owner_dir.mkdir(parents=True, exist_ok=True)
        (owner_dir / "person.json").write_text(json.dumps(payload["person"]), encoding="utf-8")
        for account, account_payload in payload["accounts"].items():
            (owner_dir / f"{account}.json").write_text(
                json.dumps(account_payload),
                encoding="utf-8",
            )

    aws_objects: dict[str, bytes] = {}
    for owner, payload in owners.items():
        aws_objects[f"accounts/{owner}/person.json"] = json.dumps(payload["person"]).encode("utf-8")
        for account, account_payload in payload["accounts"].items():
            aws_objects[f"accounts/{owner}/{account}.json"] = json.dumps(account_payload).encode(
                "utf-8"
            )

    return {
        "accounts_root": accounts_root,
        "owners": owners,
        "aws_objects": aws_objects,
    }


@pytest.fixture(autouse=True)
def restore_boto3_module():
    original = sys.modules.get("boto3")
    yield
    if original is None:
        sys.modules.pop("boto3", None)
    else:
        sys.modules["boto3"] = original


def _configure_local(monkeypatch: pytest.MonkeyPatch, accounts_root: Path) -> None:
    cfg = Config()
    cfg.app_env = "local"
    cfg.disable_auth = False
    cfg.repo_root = accounts_root.parent
    cfg.accounts_root = accounts_root
    monkeypatch.setattr(data_loader, "config", cfg)
    monkeypatch.delenv(data_loader.DATA_BUCKET_ENV, raising=False)


def _configure_aws(
    monkeypatch: pytest.MonkeyPatch,
    accounts_root: Path,
    aws_objects: dict[str, bytes],
) -> None:
    cfg = Config()
    cfg.app_env = "aws"
    cfg.disable_auth = False
    cfg.repo_root = accounts_root.parent
    cfg.accounts_root = accounts_root
    monkeypatch.setattr(data_loader, "config", cfg)
    monkeypatch.setenv(data_loader.DATA_BUCKET_ENV, "parity-bucket")
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(client=lambda service: MockS3Client(aws_objects)),
    )


def _normalise_owner_listing(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        [
            {
                "owner": str(entry["owner"]).lower(),
                "accounts": sorted(str(account).lower() for account in entry.get("accounts", [])),
                "full_name": entry.get("full_name"),
                "email": entry.get("email"),
            }
            for entry in entries
        ],
        key=lambda item: item["owner"],
    )


@pytest.mark.parametrize(
    ("owner", "account"),
    [("Alice", "ISA"), ("Alice", "GIA"), ("bob", "SIPP")],
)
def test_load_account_matches_between_local_and_mocked_aws(
    monkeypatch: pytest.MonkeyPatch,
    shared_provider_dataset: dict[str, object],
    owner: str,
    account: str,
) -> None:
    accounts_root = shared_provider_dataset["accounts_root"]
    aws_objects = shared_provider_dataset["aws_objects"]

    _configure_local(monkeypatch, accounts_root)
    local_data = data_loader.load_account(owner, account, data_root=accounts_root)

    _configure_aws(monkeypatch, accounts_root, aws_objects)
    aws_data = data_loader.load_account(owner, account, data_root=accounts_root)

    assert aws_data == local_data


@pytest.mark.parametrize("owner", ["Alice", "bob"])
def test_load_person_meta_matches_between_local_and_mocked_aws(
    monkeypatch: pytest.MonkeyPatch,
    shared_provider_dataset: dict[str, object],
    owner: str,
) -> None:
    accounts_root = shared_provider_dataset["accounts_root"]
    aws_objects = shared_provider_dataset["aws_objects"]

    _configure_local(monkeypatch, accounts_root)
    local_meta = data_loader.load_person_meta(owner, data_root=accounts_root)

    _configure_aws(monkeypatch, accounts_root, aws_objects)
    aws_meta = data_loader.load_person_meta(owner, data_root=accounts_root)

    assert aws_meta == local_meta


def test_list_plots_matches_between_local_and_mocked_aws_after_normalisation(
    monkeypatch: pytest.MonkeyPatch,
    shared_provider_dataset: dict[str, object],
) -> None:
    accounts_root = shared_provider_dataset["accounts_root"]
    aws_objects = shared_provider_dataset["aws_objects"]
    viewer = "bob@example.com"

    _configure_local(monkeypatch, accounts_root)
    local_entries = data_loader.list_plots(data_root=accounts_root, current_user=viewer)

    _configure_aws(monkeypatch, accounts_root, aws_objects)
    aws_entries = data_loader.list_plots(data_root=accounts_root, current_user=viewer)

    assert _normalise_owner_listing(aws_entries) == _normalise_owner_listing(local_entries)
    assert _normalise_owner_listing(local_entries) == [
        {
            "owner": "alice",
            "accounts": ["gia", "isa"],
            "full_name": "Alice Example",
            "email": "alice@example.com",
        },
        {
            "owner": "bob",
            "accounts": ["sipp"],
            "full_name": "Bob Example",
            "email": "bob@example.com",
        },
    ]
