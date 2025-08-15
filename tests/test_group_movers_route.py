import backend.common.instrument_api as ia
from backend.local_api.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


def test_group_movers_endpoint(monkeypatch):
    def fake_summaries(slug: str):
        assert slug == "demo"
        return [{"ticker": "AAA"}, {"ticker": "BBB"}]

    def fake_top_movers(tickers, days, limit):
        assert tickers == ["AAA", "BBB"]
        assert days == 7
        assert limit == 5
        return {
            "gainers": [{"ticker": "AAA", "name": "AAA", "change_pct": 5}],
            "losers": [{"ticker": "BBB", "name": "BBB", "change_pct": -3}],
        }

    monkeypatch.setattr(ia, "instrument_summaries_for_group", fake_summaries)
    monkeypatch.setattr(ia, "top_movers", fake_top_movers)

    resp = client.get("/portfolio-group/demo/movers?days=7&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert [g["ticker"] for g in data["gainers"]] == ["AAA"]
    assert [l["ticker"] for l in data["losers"]] == ["BBB"]
