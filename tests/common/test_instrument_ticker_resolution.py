from backend.common import instruments


def test_resolver_prefers_existing_metadata_without_creating(monkeypatch):
    monkeypatch.setattr(
        instruments,
        "get_instrument_meta",
        lambda ticker: (
            {"ticker": ticker, "exchange": "US", "currency": "USD"} if ticker == "MSFT.US" else {}
        ),
    )
    create = monkeypatch.setattr(instruments, "_auto_create_instrument_meta", lambda ticker: None)

    assert instruments.resolve_instrument_ticker("MSFT") == "MSFT.US"
    assert create is None


def test_resolver_explicitly_creates_and_persists_first_valid_candidate(monkeypatch):
    monkeypatch.setattr(instruments, "get_instrument_meta", lambda ticker: {})
    attempted: list[str] = []

    def create(ticker: str):
        attempted.append(ticker)
        if ticker == "ADBE.US":
            return {"ticker": ticker, "exchange": "US", "currency": "USD"}
        return None

    monkeypatch.setattr(instruments, "_auto_create_instrument_meta", create)

    assert (
        instruments.resolve_instrument_ticker("ADBE.L", exchanges=("L", "US"), create_missing=True)
        == "ADBE.US"
    )
    assert attempted == ["ADBE.L", "ADBE.US"]


def test_resolver_rejects_placeholder_metadata(monkeypatch):
    monkeypatch.setattr(
        instruments,
        "get_instrument_meta",
        lambda ticker: {"ticker": ticker, "exchange": "L", "name": ticker},
    )

    assert instruments.resolve_instrument_ticker("BMNR1F3", exchanges=("L", "US")) is None


def test_resolver_honours_persisted_exchange_alias_not_in_canonical_list(monkeypatch):
    """Metadata persisted under a non-canonical exchange (e.g. ``N`` for NYSE)
    must still be found instead of falling through to an incorrect ``.L``
    ticker (#6310)."""
    monkeypatch.setattr(instruments, "_persisted_metadata_exchanges", lambda symbol: ("N",))
    monkeypatch.setattr(
        instruments,
        "get_instrument_meta",
        lambda ticker: (
            {"ticker": ticker, "exchange": "N", "currency": "USD"} if ticker == "PFE.N" else {}
        ),
    )

    assert instruments.resolve_instrument_ticker("PFE", exchanges=("L", "US")) == "PFE.N"


def test_resolver_finds_genuine_lse_ticker_from_real_persisted_metadata(monkeypatch, tmp_path):
    """Unmocked end-to-end check: a real LSE holding with informative metadata
    already on disk (e.g. ``3IN.L``) must resolve to itself, not be treated
    as needing reconciliation (#6310)."""
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    instruments.get_instrument_meta.cache_clear()
    instruments._persisted_metadata_exchanges.cache_clear()
    instruments.save_instrument_meta(
        "3IN",
        "L",
        {"ticker": "3IN.L", "exchange": "L", "name": "3i Infrastructure", "currency": "GBP"},
    )

    assert instruments.resolve_instrument_ticker("3IN") == "3IN.L"
