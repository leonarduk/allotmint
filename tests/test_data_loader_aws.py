import io
import sys
from types import SimpleNamespace

import backend.common.data_loader as dl


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


def test_load_person_meta_from_s3(monkeypatch):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            if Key == "accounts/Alice/person.json":
                return {"Body": io.BytesIO(b"{\"dob\": \"1980\"}")}
            raise Exception("NoSuchKey")

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    assert dl.load_person_meta("Alice") == {"dob": "1980"}
    assert dl.load_person_meta("Bob") == {}
