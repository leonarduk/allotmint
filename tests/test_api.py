import pytest
from fastapi.testclient import TestClient
from backend.local_api.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert "env" in data


def test_owners():
    resp = client.get("/owners")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_groups():
    resp = client.get("/groups")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_valid_group_portfolio():
    groups = client.get("/groups").json()
    assert groups, "No groups found"
    slug = groups[0]["slug"]
    resp = client.get(f"/portfolio-group/{slug}")
    assert resp.status_code == 200


def test_invalid_group_portfolio():
    resp = client.get("/portfolio-group/doesnotexist")
    assert resp.status_code == 404


def test_valid_portfolio():
    groups = client.get("/groups").json()
    first_owner = groups[0]["members"][0]
    resp = client.get(f"/portfolio/{first_owner}")
    assert resp.status_code == 200


def test_invalid_portfolio():
    resp = client.get("/portfolio/noone")
    assert resp.status_code == 404


def test_valid_account():
    groups = client.get("/groups").json()
    first_owner = groups[0]["members"][0]
    for account in ["isa", "sipp"]:
        resp = client.get(f"/account/{first_owner}/{account}")
        if resp.status_code == 200:
            return
    pytest.skip("No valid account found for test owner")


def test_invalid_account():
    resp = client.get("/account/noone/noacct")
    assert resp.status_code == 404


def test_prices_refresh():
    resp = client.post("/prices/refresh")
    assert resp.status_code == 200
    assert "status" in resp.json()


def test_group_instruments():
    groups = client.get("/groups").json()
    slug = groups[0]["slug"]
    resp = client.get(f"/portfolio-group/{slug}/instruments")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_instrument_detail_valid():
    groups = client.get("/groups").json()
    slug = groups[0]["slug"]
    instruments = client.get(f"/portfolio-group/{slug}/instruments").json()
    if not instruments:
        pytest.skip("No instruments available for this group")

    for inst in instruments:
        ticker = inst["ticker"]
        resp = client.get(f"/portfolio-group/{slug}/instrument/{ticker}")
        if resp.status_code == 200:
            json = resp.json()
            assert "prices" in json and isinstance(json["prices"], list)
            assert "positions" in json and isinstance(json["positions"], list)
            return
    pytest.skip("No instrument with available price data")


def test_instrument_detail_not_found():
    groups = client.get("/groups").json()
    slug = groups[0]["slug"]
    resp = client.get(f"/portfolio-group/{slug}/instrument/FAKETICK")
    assert resp.status_code == 404


def test_yahoo_timeseries_html():
    resp = client.get("/timeseries/html?ticker=AAPL&period=1y&interval=1d")
    assert resp.status_code == 200
    assert "<html>" in resp.text.lower()


# @pytest.mark.parametrize("format", ["html", "json", "csv"])
# def test_ft_timeseries(format):
#     resp = client.get(
#         f"/timeseries/ft?ticker=GB00B45Q9038:GBP&period=1y&interval=1d&format={format}"
#     )
#     # FT sometimes rate-limits or fails, so accept 404 if no data
#     assert resp.status_code in (200, 404)
