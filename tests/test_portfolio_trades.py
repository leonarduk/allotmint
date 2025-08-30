import sys
from types import SimpleNamespace

import backend.common.portfolio as portfolio
from botocore.exceptions import ClientError


def test_load_trades_aws_success(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    monkeypatch.setattr(portfolio.config, "app_env", "aws", raising=False)

    body_bytes = b"date,ticker,units\n2024-02-01,AAPL,5\n"

    class FakeBody:
        def read(self):
            return body_bytes

    def fake_get_object(*, Bucket, Key):
        assert Bucket == "bucket"
        assert Key == "accounts/alice/trades.csv"
        return {"Body": FakeBody()}

    def fake_client(name):
        assert name == "s3"
        return SimpleNamespace(get_object=fake_get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    trades = portfolio.load_trades("alice")
    assert trades == [{"date": "2024-02-01", "ticker": "AAPL", "units": "5"}]


def test_load_trades_aws_missing(monkeypatch, caplog):
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    monkeypatch.setattr(portfolio.config, "app_env", "aws", raising=False)

    def fake_get_object(*, Bucket, Key):
        raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject")

    def fake_client(name):
        assert name == "s3"
        return SimpleNamespace(get_object=fake_get_object)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    with caplog.at_level("WARNING"):
        trades = portfolio.load_trades("bob")
    assert trades == []
    assert any("Failed to fetch trades" in r.message for r in caplog.records)
