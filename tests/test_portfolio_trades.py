import backend.common.portfolio as portfolio


def test_load_trades_aws_success(s3_bucket, monkeypatch):
    s3, bucket = s3_bucket
    monkeypatch.setattr(portfolio.config, "app_env", "aws", raising=False)
    body = "date,ticker,units\n2024-02-01,AAPL,5\n"
    s3.put_object(Bucket=bucket, Key="accounts/alice/trades.csv", Body=body)
    trades = portfolio.load_trades("alice")
    assert trades == [{"date": "2024-02-01", "ticker": "AAPL", "units": "5"}]


def test_load_trades_aws_missing(s3_bucket, monkeypatch):
    _, _ = s3_bucket  # ensure bucket exists
    monkeypatch.setattr(portfolio.config, "app_env", "aws", raising=False)
    trades = portfolio.load_trades("bob")
    assert trades == []
