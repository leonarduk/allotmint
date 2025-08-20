import sys
from types import SimpleNamespace

import backend.common.portfolio as portfolio


class FakeClientError(Exception):
    pass


def _patch_boto(monkeypatch, get_object):
    def fake_client(name):
        assert name == "s3"
        return SimpleNamespace(get_object=get_object)

    fake_ex = SimpleNamespace(BotoCoreError=Exception, ClientError=FakeClientError)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))
    monkeypatch.setitem(sys.modules, "botocore", SimpleNamespace(exceptions=fake_ex))
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_ex)


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

    _patch_boto(monkeypatch, fake_get_object)

    trades = portfolio.load_trades("alice")
    assert trades == [{"date": "2024-02-01", "ticker": "AAPL", "units": "5"}]


def test_load_trades_aws_client_error(monkeypatch, caplog):
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    monkeypatch.setattr(portfolio.config, "app_env", "aws", raising=False)

    def fake_get_object(*, Bucket, Key):
        raise FakeClientError("boom")

    _patch_boto(monkeypatch, fake_get_object)

    with caplog.at_level("ERROR"):
        trades = portfolio.load_trades("bob")
    assert trades == []
    assert "Failed to fetch trades" in caplog.text
