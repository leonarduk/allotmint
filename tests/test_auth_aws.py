import io
import sys
from types import SimpleNamespace

import backend.auth as auth
import backend.common.data_loader as dl


def test_allowed_emails_from_s3(monkeypatch):
    monkeypatch.setattr(auth.config, "app_env", "aws", raising=False)
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
                    {"Key": "accounts/Bob/person.json"},
                    {"Key": "accounts/Carol/person.json"},
                ]
            }

        def get_object(Bucket, Key):
            assert Bucket == "bucket"
            if Key == "accounts/Alice/person.json":
                return {"Body": io.BytesIO(b'{"email": "alice@example.com"}')}
            if Key == "accounts/Bob/person.json":
                return {"Body": io.BytesIO(b'{"email": "bob@example.com"}')}
            if Key == "accounts/Carol/person.json":
                return {"Body": io.BytesIO(b'{"email": "carol@example.com"}')}
            return {"Body": io.BytesIO(b"")}

        return SimpleNamespace(list_objects_v2=list_objects_v2, get_object=get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    assert auth._allowed_emails() == {
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
    }


def test_allowed_emails_logs_s3_error(monkeypatch, caplog):
    monkeypatch.setattr(auth.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    class FakeS3:
        def list_objects_v2(self, **kwargs):  # noqa: ARG002 - kwargs for API parity
            raise auth.BotoCoreError()

    def fake_client(name):
        assert name == "s3"
        return FakeS3()

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    with caplog.at_level("ERROR"):
        emails = auth._allowed_emails()

    assert emails == set()
    assert any("Failed to list allowed emails from S3" in record.message for record in caplog.records)
