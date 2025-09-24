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


def test_list_aws_plots_demo_only_when_unauthenticated(monkeypatch):
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setattr(dl.config, "disable_auth", False, raising=False)

    def fake_client(name):
        assert name == "s3"

        def list_objects_v2(**kwargs):
            assert kwargs["Bucket"] == "bucket"
            assert kwargs["Prefix"] == dl.PLOTS_PREFIX
            return {
                "Contents": [
                    {"Key": "accounts/demo/ISA.json"},
                    {"Key": "accounts/Real/GIA.json"},
                ]
            }

        return SimpleNamespace(list_objects_v2=list_objects_v2)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    expected = [{"owner": "demo", "accounts": ["ISA"]}]
    assert dl._list_aws_plots() == expected


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
