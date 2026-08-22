"""Coverage for the route-only instrument_type population (allotmint#6876).

Deliberately does not import from ``allotmint_pro`` (unlike
``tests/routes/test_screener.py``, which importorskips when the private
package isn't installed) so this stays green in public/free-tier CI.
"""

from backend.routes import screener


def test_apply_instrument_type_populates_from_security_meta(monkeypatch):
    monkeypatch.setattr(
        screener,
        "get_security_meta",
        lambda ticker: {"instrument_type": "stock"} if ticker == "AAA" else None,
    )

    rows = [{"ticker": "AAA"}, {"ticker": "BBB"}]
    screener._apply_instrument_type(rows)

    assert rows[0]["instrument_type"] == "stock"
    assert rows[1]["instrument_type"] is None


def test_ranked_fundamentals_accepts_instrument_type():
    model = screener.RankedFundamentals(ticker="AAA", rank=1, instrument_type="etf")
    assert model.instrument_type == "etf"

    default_model = screener.RankedFundamentals(ticker="BBB", rank=2)
    assert default_model.instrument_type is None
