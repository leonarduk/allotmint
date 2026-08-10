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
