from fastapi.testclient import TestClient

from backend.config import config


def test_tax_harvest_route(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)
    dummy_trades = [{"ticker": "AAA", "basis": 100.0, "price": 90.0}]
    monkeypatch.setattr(
        "backend.routes.tax.harvest_losses",
        lambda positions, threshold: dummy_trades,
    )
    from backend.app import create_app
    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/tax/harvest",
            json={
                "positions": [{"ticker": "AAA", "basis": 100, "price": 90}],
                "threshold": 0.5,
            },
        )
    assert resp.status_code == 200
    assert resp.json() == {"trades": dummy_trades}


def test_tax_allowances_route(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr("backend.routes.tax.current_tax_year", lambda: 2024)
    allowances = {"isa": {"limit": 20000, "used": 5000, "remaining": 15000}}
    monkeypatch.setattr(
        "backend.routes.tax.remaining_allowances", lambda owner, ty: allowances
    )
    from backend.app import create_app
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/tax/allowances")
        assert resp.status_code == 200
        assert resp.json() == {
            "owner": "demo",
            "tax_year": 2024,
            "allowances": allowances,
        }
        resp = client.get("/tax/allowances", params={"owner": "bob"})
        assert resp.status_code == 200
        assert resp.json() == {
            "owner": "bob",
            "tax_year": 2024,
            "allowances": allowances,
        }


def test_tax_allowances_route_with_auth(monkeypatch):
    import importlib

    import backend.auth as auth_module

    original_disable_auth = config.disable_auth
    original_skip_snapshot = config.skip_snapshot_warm
    config.disable_auth = False
    config.skip_snapshot_warm = True

    monkeypatch.setattr(auth_module, "get_current_user", lambda: "alice")

    import backend.routes.tax as tax_module
    import backend.app as app_module

    tax_module = importlib.reload(tax_module)
    app_module = importlib.reload(app_module)

    allowances = {"isa": {"limit": 20000, "used": 5000, "remaining": 15000}}
    monkeypatch.setattr(tax_module, "current_tax_year", lambda: 2024)
    monkeypatch.setattr(
        tax_module,
        "remaining_allowances",
        lambda owner, tax_year: allowances,
    )

    try:
        app = app_module.create_app()
        with TestClient(app) as client:
            resp = client.get("/tax/allowances")
            assert resp.status_code == 200
            assert resp.json() == {
                "owner": "alice",
                "tax_year": 2024,
                "allowances": allowances,
            }

            resp = client.get("/tax/allowances", params={"owner": "bob"})
            assert resp.status_code == 200
            assert resp.json() == {
                "owner": "bob",
                "tax_year": 2024,
                "allowances": allowances,
            }
    finally:
        config.disable_auth = original_disable_auth
        config.skip_snapshot_warm = original_skip_snapshot
        importlib.reload(tax_module)
        importlib.reload(app_module)
