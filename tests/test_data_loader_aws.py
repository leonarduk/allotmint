import builtins
import io
import sys
from types import SimpleNamespace

import backend.common.data_loader as dl
from botocore.exceptions import ClientError
import pytest


@pytest.fixture
def cleanup_boto3_module():
    original = sys.modules.get("boto3")
    yield
    if original is None:
        sys.modules.pop("boto3", None)
    else:
        sys.modules["boto3"] = original


def test_list_aws_plots(monkeypatch):
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def list_objects_v2(**kwargs):
            assert kwargs["Bucket"] == "bucket"
            assert kwargs["Prefix"] == dl.PLOTS_PREFIX
            return {
                "Contents": [
                    {"Key": "accounts/Alice/ISA.json"},
                    {"Key": "accounts/Alice/person.json"},
                    {"Key": "accounts/Bob/GIA.json"},
                ]
            }

        return SimpleNamespace(list_objects_v2=list_objects_v2)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    expected = [
        {"owner": "Alice", "accounts": ["ISA"]},
        {"owner": "Bob", "accounts": ["GIA"]},
    ]
    assert dl._list_aws_plots() == expected


def test_list_aws_plots_missing_boto(monkeypatch, cleanup_boto3_module):
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")
    monkeypatch.delitem(sys.modules, "boto3", raising=False)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3":
            raise ModuleNotFoundError("No module named 'boto3'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert dl._list_aws_plots() == []


def test_list_aws_plots_filters_without_auth(monkeypatch):
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setattr(dl.config, "disable_auth", False, raising=False)
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)

    def fake_client(name):
        assert name == "s3"

        def list_objects_v2(**kwargs):
            assert kwargs["Bucket"] == "bucket"
            assert kwargs["Prefix"] == dl.PLOTS_PREFIX
            return {
                "Contents": [
                    {"Key": "accounts/Alice/ISA.json"},
                    {"Key": "accounts/Alice/person.json"},
                    {"Key": "accounts/Bob/GIA.json"},
                    {"Key": "accounts/Eve/JISA.json"},
                    {"Key": "accounts/Eve/person.json"},
                ]
            }

        def get_object(Bucket, Key):
            assert Bucket == "bucket"
            if Key == "accounts/Alice/person.json":
                return {"Body": io.BytesIO(b'{"viewers": ["Bob"]}')}
            if Key == "accounts/Eve/person.json":
                return {"Body": io.BytesIO(b'{"viewers": []}')}
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "get_object")

        return SimpleNamespace(list_objects_v2=list_objects_v2, get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    expected = [
        {"owner": "Alice", "accounts": ["ISA"]},
        {"owner": "Bob", "accounts": ["GIA"]},
    ]
    assert dl._list_aws_plots(current_user="Bob") == expected


def test_list_aws_plots_filters_special_directories(monkeypatch):
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setattr(dl.config, "disable_auth", True, raising=False)

    def fake_client(name):
        assert name == "s3"

        def list_objects_v2(**kwargs):
            assert kwargs["Bucket"] == "bucket"
            assert kwargs["Prefix"] == dl.PLOTS_PREFIX
            return {
                "Contents": [
                    {"Key": "accounts/demo/ISA.json"},
                    {"Key": "accounts/.idea/ignored.json"},
                    {"Key": "accounts/Real/GIA.json"},
                ]
            }

        return SimpleNamespace(list_objects_v2=list_objects_v2)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    expected = [{"owner": "Real", "accounts": ["GIA"]}]
    assert dl._list_aws_plots() == expected


def test_list_aws_plots_pagination(monkeypatch):
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    responses = [
        {
            "Contents": [
                {"Key": "accounts/Alice/ISA.json"},
                {"Key": "accounts/Alice/person.json"},
            ],
            "IsTruncated": True,
            "NextContinuationToken": "token-1",
        },
        {
            "Contents": [
                {"Key": "accounts/Alice/isa.json"},
                {"Key": "accounts/Bob/GIA.json"},
            ],
            "IsTruncated": True,
            "NextContinuationToken": "token-2",
        },
        {
            "Contents": [
                {"Key": "accounts/Bob/gia.json"},
                {"Key": "accounts/Carol/401k.json"},
            ],
            "IsTruncated": False,
        },
    ]

    calls = []

    def fake_client(name):
        assert name == "s3"

        def list_objects_v2(**kwargs):
            index = len(calls)
            calls.append(kwargs)
            if index == 0:
                assert "ContinuationToken" not in kwargs
            else:
                expected_token = responses[index - 1]["NextContinuationToken"]
                assert kwargs["ContinuationToken"] == expected_token
            return responses[index]

        return SimpleNamespace(list_objects_v2=list_objects_v2)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    expected = [
        {"owner": "Alice", "accounts": ["ISA"]},
        {"owner": "Bob", "accounts": ["GIA"]},
        {"owner": "Carol", "accounts": ["401k"]},
    ]

    assert dl._list_aws_plots() == expected
    assert len(calls) == 3


def test_load_account_from_s3(monkeypatch):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            assert Bucket == "bucket"
            assert Key == "accounts/Alice/ISA.json"
            return {"Body": io.BytesIO(b"{\"balance\": 10}")}

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    assert dl.load_account("Alice", "ISA") == {"balance": 10}


def test_load_account_missing_bucket(monkeypatch):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.delenv(dl.DATA_BUCKET_ENV, raising=False)

    with pytest.raises(FileNotFoundError) as exc:
        dl.load_account("owner", "acct")

    assert (
        str(exc.value)
        == f"Missing {dl.DATA_BUCKET_ENV} env var for AWS account loading"
    )


def test_load_account_empty_payload(monkeypatch, cleanup_boto3_module):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            assert Bucket == "bucket"
            assert Key == "accounts/owner/acct.json"
            return {"Body": io.BytesIO(b"   ")}

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    with pytest.raises(ValueError) as exc:
        dl.load_account("owner", "acct")

    assert str(exc.value) == "Empty JSON file: s3://bucket/accounts/owner/acct.json"


def test_load_person_meta_from_s3(monkeypatch):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            if Key == "accounts/Alice/person.json":
                return {"Body": io.BytesIO(b"{\"dob\": \"1980\"}")}
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "get_object")

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    assert dl.load_person_meta("Alice") == {"dob": "1980", "viewers": []}
    assert dl.load_person_meta("Bob") == {}


def test_load_person_meta_missing_bucket(monkeypatch, cleanup_boto3_module):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.delenv(dl.DATA_BUCKET_ENV, raising=False)

    assert dl.load_person_meta("Alice") == {}


def test_load_person_meta_boto_failure(monkeypatch, cleanup_boto3_module):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            raise RuntimeError("boom")

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    assert dl.load_person_meta("Alice") == {}


def test_list_plots_delegates_to_aws(monkeypatch):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)

    sentinel = object()

    def fake_aws(current_user=None):
        assert current_user == "alice"
        return sentinel

    monkeypatch.setattr(dl, "_list_aws_plots", fake_aws)

    assert dl.list_plots(current_user="alice") is sentinel


def test_list_plots_uses_local_when_not_aws(monkeypatch):
    monkeypatch.setattr(dl.config, "app_env", "local", raising=False)

    sentinel = object()

    def fake_local(data_root=None, current_user=None):
        assert data_root == "root"
        assert current_user == "bob"
        return sentinel

    monkeypatch.setattr(dl, "_list_local_plots", fake_local)

    assert dl.list_plots(data_root="root", current_user="bob") is sentinel
