import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common.rebalance import suggest_trades


def test_suggest_trades_valid_target_sum():
    actual = {"AAA": 100.0, "BBB": 50.0}
    target = {"AAA": 0.5, "BBB": 0.5}
    trades = suggest_trades(actual, target)
    assert trades == [
        {"ticker": "AAA", "action": "sell", "amount": 25.0},
        {"ticker": "BBB", "action": "buy", "amount": 25.0},
    ]


def test_suggest_trades_invalid_target_sum():
    actual = {"AAA": 100.0}
    target = {"AAA": 0.9}
    with pytest.raises(ValueError):
        suggest_trades(actual, target)


def test_suggest_trades_negative_target_weight():
    actual = {"AAA": 100.0, "BBB": 50.0}
    target = {"AAA": -0.1, "BBB": 1.1}
    with pytest.raises(ValueError, match="AAA"):
        suggest_trades(actual, target)


def test_suggest_trades_target_weight_over_one():
    actual = {"AAA": 100.0, "BBB": 50.0}
    target = {"AAA": 1.5, "BBB": -0.5}
    with pytest.raises(ValueError, match="AAA"):
        suggest_trades(actual, target)


# ---------------------------------------------------------------- #9446 routes


def _owner_client(monkeypatch, tmp_path):
    from backend.routes import rebalance as rebalance_route

    (tmp_path / "alex").mkdir()
    portfolio = {
        "accounts": [
            {
                "account_type": "ISA",
                "holdings": [
                    {"ticker": "CASH.GBP", "market_value_gbp": 200.0, "instrument_type": "Cash"},
                    {"ticker": "EQ1", "market_value_gbp": 800.0, "asset_class": "equity"},
                ],
            }
        ]
    }
    monkeypatch.setattr(rebalance_route.portfolio_mod, "build_owner_portfolio", lambda owner, root: portfolio)
    app = FastAPI()
    app.include_router(rebalance_route.router)
    app.state.accounts_root = tmp_path
    return TestClient(app)


def test_policy_put_get_round_trip(monkeypatch, tmp_path):
    client = _owner_client(monkeypatch, tmp_path)
    assert client.get("/rebalance/alex/policy").json() == {"targets": {}, "tolerance_pct": 5.0}

    resp = client.put("/rebalance/alex/policy", json={"targets": {"equity": 60, "bond": 40}, "tolerance_pct": 3})
    assert resp.status_code == 200
    assert client.get("/rebalance/alex/policy").json() == {
        "targets": {"equity": 60.0, "bond": 40.0},
        "tolerance_pct": 3.0,
    }


def test_policy_put_rejects_targets_not_summing_to_100(monkeypatch, tmp_path):
    client = _owner_client(monkeypatch, tmp_path)
    resp = client.put("/rebalance/alex/policy", json={"targets": {"equity": 60}})
    assert resp.status_code == 400
    assert "100%" in resp.json()["detail"]


def test_plan_uses_stored_policy(monkeypatch, tmp_path):
    client = _owner_client(monkeypatch, tmp_path)
    client.put("/rebalance/alex/policy", json={"targets": {"equity": 50, "bond": 50}})
    plan = client.get("/rebalance/alex/plan").json()
    assert plan["total_value"] == 1000.0
    assert [(t["account"], t["action"], t["asset_class"], t["amount"]) for t in plan["trades"]] == [
        ("ISA", "sell", "equity", 300.0),
        ("ISA", "buy", "bond", 500.0),
    ]


def test_new_cash_route(monkeypatch, tmp_path):
    client = _owner_client(monkeypatch, tmp_path)
    client.put("/rebalance/alex/policy", json={"targets": {"equity": 50, "bond": 50}})
    resp = client.get("/rebalance/alex/new-cash", params={"amount": 100, "account": "0"})
    assert resp.status_code == 200
    assert [(t["asset_class"], t["amount"]) for t in resp.json()["trades"]] == [("bond", 100.0)]

    resp = client.get("/rebalance/alex/new-cash", params={"amount": 100, "account": "7"})
    assert resp.status_code == 400


def test_owner_routes_unknown_owner_returns_404(monkeypatch, tmp_path):
    from fastapi.responses import JSONResponse

    from backend.common.errors import AppError

    client = _owner_client(monkeypatch, tmp_path)
    # Mirror the app-level AppError handler (backend/bootstrap/middleware.py).
    client.app.add_exception_handler(
        AppError,
        lambda request, exc: JSONResponse(status_code=exc.status_code, content={"detail": exc.safe_detail}),
    )
    for method, path in [
        ("get", "/rebalance/nobody/policy"),
        ("get", "/rebalance/nobody/plan"),
        ("get", "/rebalance/nobody/new-cash?amount=1&account=0"),
    ]:
        assert getattr(client, method)(path).status_code == 404, path
    assert client.put("/rebalance/nobody/policy", json={"targets": {}}).status_code == 404


def test_policy_put_refuses_corrupt_settings_file(monkeypatch, tmp_path):
    client = _owner_client(monkeypatch, tmp_path)
    (tmp_path / "alex" / "settings.json").write_text("{not json")
    resp = client.put("/rebalance/alex/policy", json={"targets": {"equity": 100}})
    assert resp.status_code == 409
    assert (tmp_path / "alex" / "settings.json").read_text() == "{not json"
