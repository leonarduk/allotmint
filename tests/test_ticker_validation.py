import json
from pathlib import Path

from backend.common import instruments
from backend.timeseries import ticker_validator
from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_invalid_ticker_skipped(monkeypatch, tmp_path):
    log_file = tmp_path / "skipped.log"
    monkeypatch.setattr(ticker_validator, "SKIPPED_TICKERS_FILE", log_file)

    df = fetch_meta_timeseries("ZZZZZZ", "L")
    assert df.empty
    assert log_file.exists()
    content = log_file.read_text().strip()
    assert "ZZZZZZ" in content


# Shape of allotmint-data's ``events/market_events.json`` (a separate repo):
# bare US tickers in ``proxy_index.ticker`` and each ``reference_index``.
_MARKET_EVENTS_SAMPLE = {
    "proxy_index": {"ticker": "SPY", "name": "SPDR S&P 500 ETF"},
    "events": [
        {"date": "2008-09-15", "description": "Lehman", "reference_index": "SPY"},
        {"date": "2020-02-19", "description": "COVID-19"},
    ],
}


def _bundled_proxy_tickers() -> set[str]:
    from backend.routes import events as events_route
    from backend.routes import scenario

    events = json.loads((_REPO_ROOT / "data" / "events.json").read_text(encoding="utf-8"))
    proxies = {e["proxy_index"] for e in events if e.get("proxy_index")}
    # market_events.json proxies go through the same mapping the route uses.
    market = {d["proxy_index"] for d in events_route._event_details(_MARKET_EVENTS_SAMPLE).values()}
    return proxies | market | {scenario._DEFAULT_PROXY_INDEX}


def test_bundled_scenario_proxies_pass_ticker_validation(monkeypatch):
    """Scenario proxy indices must not be skipped as unrecognized tickers (#9489)."""
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", _REPO_ROOT / "data" / "instruments")
    monkeypatch.delenv(instruments.METADATA_BUCKET_ENV, raising=False)
    instruments.get_instrument_meta.cache_clear()
    ticker_validator.is_valid_ticker.cache_clear()
    try:
        for full in _bundled_proxy_tickers():
            sym, exchange = full.split(".")
            assert ticker_validator.is_valid_ticker(sym, exchange), full
        # The guard still rejects tickers with no metadata.
        assert not ticker_validator.is_valid_ticker("ZZJUNK", "N")
    finally:
        instruments.get_instrument_meta.cache_clear()
        ticker_validator.is_valid_ticker.cache_clear()
