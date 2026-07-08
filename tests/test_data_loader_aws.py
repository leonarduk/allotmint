import builtins
import io
import logging
import os
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


@pytest.fixture(autouse=True)
def restore_config_env():
    had_disable_auth = hasattr(dl.config, "disable_auth")
    original_disable_auth = getattr(dl.config, "disable_auth", None)
    had_app_env = hasattr(dl.config, "app_env")
    original_app_env = getattr(dl.config, "app_env", None)
    original_bucket = os.environ.get(dl.DATA_BUCKET_ENV)

    yield

    if had_disable_auth:
        setattr(dl.config, "disable_auth", original_disable_auth)
    elif hasattr(dl.config, "disable_auth"):
        delattr(dl.config, "disable_auth")

    if had_app_env:
        setattr(dl.config, "app_env", original_app_env)
    elif hasattr(dl.config, "app_env"):
        delattr(dl.config, "app_env")

    if original_bucket is None:
        os.environ.pop(dl.DATA_BUCKET_ENV, None)
    else:
        os.environ[dl.DATA_BUCKET_ENV] = original_bucket


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
    owners = dl._list_aws_plots()
    assert owners == expected
    assert all("full_name" not in entry for entry in owners)


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
    owners = dl._list_aws_plots(current_user="Bob")
    assert owners == expected
    assert all("full_name" not in entry for entry in owners)


def test_list_aws_plots_blocks_anonymous(monkeypatch, cleanup_boto3_module):
    monkeypatch.setattr(dl.config, "disable_auth", False, raising=False)
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    calls = {"list_objects": False}

    def fake_client(name):
        assert name == "s3"

        def list_objects_v2(**kwargs):
            calls["list_objects"] = True
            assert kwargs["Bucket"] == "bucket"
            assert kwargs["Prefix"] == dl.PLOTS_PREFIX
            return {"Contents": [{"Key": "accounts/Alice/ISA.json"}]}

        return SimpleNamespace(list_objects_v2=list_objects_v2)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    assert dl._list_aws_plots(current_user=None) == []
    assert calls["list_objects"] is True


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
    owners = dl._list_aws_plots()
    assert owners == expected
    assert all("full_name" not in entry for entry in owners)


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

    owners = dl._list_aws_plots()
    assert owners == expected
    assert all("full_name" not in entry for entry in owners)
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


def test_load_account_falls_back_to_local(tmp_path, monkeypatch, caplog, cleanup_boto3_module):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    owner_dir = tmp_path / "owner"
    owner_dir.mkdir()
    (owner_dir / "account.json").write_text("{\"value\": 7}")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            raise RuntimeError("boom")

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    with caplog.at_level(logging.WARNING):
        data = dl.load_account("owner", "account", data_root=tmp_path)

    assert data == {"value": 7}
    assert any(
        "falling back to local file" in record.getMessage()
        and "s3://bucket/accounts/owner/account.json" in record.getMessage()
        for record in caplog.records
    )


def test_load_account_falls_back_sanitises_log_fields(
    tmp_path, monkeypatch, caplog, cleanup_boto3_module
):
    """Owner/account values are sanitised before being logged on fallback.

    Regression test for #4009: a malicious owner/account containing CRLF
    must not be able to inject fake log lines (CWE-117) into the fallback
    warning emitted by ``load_account``.
    """
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    owner = "owner\r\nFAKE LOG LINE"
    account = "acct\r\ninjected"

    owner_dir = tmp_path / "owner"
    owner_dir.mkdir()
    (owner_dir / "account.json").write_text('{"value": 7}')

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            raise RuntimeError("boom")

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    with caplog.at_level(logging.WARNING):
        with pytest.raises(FileNotFoundError):
            dl.load_account(owner, account, data_root=tmp_path)

    warning_records = [
        r for r in caplog.records if "falling back to local file" in r.getMessage()
    ]
    assert len(warning_records) == 1
    record = warning_records[0]

    assert "\r" not in record.getMessage()
    assert "\n" not in record.getMessage()
    assert record.owner == "ownerFAKE LOG LINE"
    assert record.account == "acctinjected"


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


def test_load_account_malformed_json_from_s3(monkeypatch, cleanup_boto3_module):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            assert Key == "accounts/owner/acct.json"
            return {"Body": io.BytesIO(b"not valid json {")}

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    with pytest.raises(dl.InvalidPayload):
        dl.load_account("owner", "acct")


def test_load_account_s3_unavailable_no_fallback(monkeypatch, cleanup_boto3_module):
    """ProviderUnavailable propagates when S3 fails and there is no local root."""
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            from botocore.exceptions import BotoCoreError
            raise BotoCoreError()

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))
    # Force local_root to None so the exception is not swallowed by a local fallback.
    def _raise(*a, **kw):
        raise RuntimeError("no path")

    monkeypatch.setattr(dl, "resolve_paths", _raise)

    with pytest.raises(dl.ProviderUnavailable):
        dl.load_account("owner", "acct")


def test_load_person_meta_empty_payload_from_s3(monkeypatch, cleanup_boto3_module):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            assert Key == "accounts/Alice/person.json"
            return {"Body": io.BytesIO(b"   ")}

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    assert dl.load_person_meta("Alice") == {}


def test_load_person_meta_malformed_json_from_s3(monkeypatch, cleanup_boto3_module, caplog):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            assert Key == "accounts/Alice/person.json"
            return {"Body": io.BytesIO(b"not valid json {")}

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    with caplog.at_level(logging.WARNING):
        result = dl.load_person_meta("Alice")

    assert result == {}
    assert any("person_meta_invalid_payload" in r.getMessage() for r in caplog.records)


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

    # The source JSON only contains 'dob'; _extract returns exactly the keys
    # present in the source file, so 'viewers' is not synthesised.
    assert dl.load_person_meta("Alice") == {"dob": "1980"}
    assert dl.load_person_meta("Bob") == {}


def test_load_person_meta_missing_bucket(monkeypatch, cleanup_boto3_module, caplog):
    """AWS mode with no bucket set must silently return {} with no warning logged."""
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.delenv(dl.DATA_BUCKET_ENV, raising=False)

    with caplog.at_level(logging.WARNING):
        result = dl.load_person_meta("Alice")

    assert result == {}
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


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


def test_load_person_meta_s3_unavailable_falls_back_to_local(
    tmp_path, monkeypatch, caplog, cleanup_boto3_module
):
    """When S3 is unavailable but an explicit local fallback exists, local metadata is returned."""
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    owner_dir = tmp_path / "Alice"
    owner_dir.mkdir()
    (owner_dir / "person.json").write_text('{"full_name": "Alice Local"}')

    def fake_client(name):
        assert name == "s3"

        def get_object(Bucket, Key):
            raise RuntimeError("boom")

        return SimpleNamespace(get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    with caplog.at_level(logging.WARNING):
        result = dl.load_person_meta("Alice", data_root=tmp_path)

    assert result.get("full_name") == "Alice Local"
    assert any("person_meta_provider_unavailable" in r.getMessage() for r in caplog.records)


def test_extract_person_meta_non_list_viewers_drops_key_preserves_rest(monkeypatch):
    """_extract_person_meta drops viewers when not a list but keeps other valid keys."""
    from backend.common.data_providers import _extract_person_meta
    # Non-list viewers: key is dropped, other valid fields are preserved.
    assert _extract_person_meta({"viewers": "bad", "dob": "1980"}) == {"dob": "1980"}
    assert _extract_person_meta({"viewers": "bad"}) == {}
    assert _extract_person_meta({"viewers": ["ok"]}) == {"viewers": ["ok"]}
    assert _extract_person_meta({"dob": "1980"}) == {"dob": "1980"}


def test_list_plots_delegates_to_aws(monkeypatch):
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)

    sentinel = [{"owner": "aws-owner", "accounts": ["isa"]}]

    def fake_aws(current_user=None):
        assert current_user == "alice"
        return sentinel

    monkeypatch.setattr(dl, "_list_aws_plots", fake_aws)

    result = dl.list_plots(current_user="alice")
    assert result == [dl.OwnerSummaryRecord(owner="aws-owner", accounts=["isa"])]


def test_list_plots_uses_local_when_not_aws(monkeypatch):
    monkeypatch.setattr(dl.config, "app_env", "local", raising=False)

    sentinel = [{"owner": "local-owner", "accounts": ["sipp"]}]

    def fake_local(data_root=None, current_user=None):
        assert data_root == "root"
        assert current_user == "bob"
        return sentinel

    monkeypatch.setattr(dl, "_list_local_plots", fake_local)

    result = dl.list_plots(data_root="root", current_user="bob")
    assert result == [dl.OwnerSummaryRecord(owner="local-owner", accounts=["sipp"])]
