import csv
from backend.tasks import trades


def test_persist_trades_writes_combined_csv(monkeypatch, tmp_path):
    existing = [{"date": "2024-01-01", "ticker": "AAPL", "units": "5"}]
    new_trades = [{"date": "2024-01-02", "ticker": "MSFT", "units": "3"}]

    monkeypatch.setattr(trades, "load_trades", lambda owner: existing)
    monkeypatch.setattr(trades, "_local_trades_path", lambda owner: tmp_path / owner / "trades.csv")

    saved = trades.persist_trades("alice", new_trades)
    assert saved == len(new_trades)

    csv_path = tmp_path / "alice" / "trades.csv"
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert rows == existing + new_trades


def test_lambda_handler_saves_and_alerts(monkeypatch, tmp_path):
    sample = [
        {"date": "2024-01-02", "ticker": "AAPL", "units": "5"},
        {"date": "2024-01-03", "ticker": "MSFT", "units": "2"},
    ]

    monkeypatch.setattr(trades.AlpacaAPI, "recent_trades", lambda self, since: sample)
    monkeypatch.setattr(trades, "load_trades", lambda owner: [])
    monkeypatch.setattr(trades, "_local_trades_path", lambda owner: tmp_path / owner / "trades.csv")

    alerts = []
    monkeypatch.setattr(trades, "publish_alert", lambda alert: alerts.append(alert))

    monkeypatch.setenv("ALPACA_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET", "secret")

    result = trades.lambda_handler({"owner": "bob"}, None)
    assert result == {"count": 2}
    assert alerts == [
        {"ticker": "IMPORT", "change_pct": 0.0, "message": "Imported 2 trades for bob"}
    ]

    csv_path = tmp_path / "bob" / "trades.csv"
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert rows == sample
