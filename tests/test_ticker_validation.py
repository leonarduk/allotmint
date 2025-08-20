from backend.timeseries import ticker_validator
from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries


def test_invalid_ticker_skipped(monkeypatch, tmp_path):
    log_file = tmp_path / "skipped.log"
    monkeypatch.setattr(ticker_validator, "SKIPPED_TICKERS_FILE", log_file)

    df = fetch_meta_timeseries("ZZZZZZ", "L")
    assert df.empty
    assert log_file.exists()
    content = log_file.read_text().strip()
    assert "ZZZZZZ" in content
