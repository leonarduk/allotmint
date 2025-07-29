import pytest
from fastapi.testclient import TestClient

from backend.local_api.main import app

client = TestClient(app)


def validate_timeseries(prices):
    assert isinstance(prices, list)
    assert len(prices) > 0
    first = prices[0]
    assert "date" in first and "close" in first
    dates = [p["date"] for p in prices]
    assert dates == sorted(dates), "Dates are not in ascending order"


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data and data["status"] == "ok"
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
    group_slug = groups[0]["slug"]
    resp = client.get(f"/portfolio-group/{group_slug}")
    assert resp.status_code == 200


def test_invalid_group_portfolio():
    resp = client.get("/portfolio-group/doesnotexist")
    assert resp.status_code == 404


def test_valid_portfolio():
    groups = client.get("/groups").json()
    assert groups, "No groups found"
    first_name = groups[0]["members"][0]
    resp = client.get(f"/portfolio/{first_name}")
    assert resp.status_code == 200


def test_invalid_portfolio():
    resp = client.get("/portfolio/noone")
    assert resp.status_code == 404


def test_valid_account():
    groups = client.get("/groups").json()
    assert groups, "No groups found"
    first_name = groups[0]["members"][0]
    # You'll need to replace with a valid account name like "ISA" or "SIPP"
    resp = client.get(f"/account/{first_name}/ISA")
    assert resp.status_code == 200


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
    instruments = resp.json()
    assert isinstance(instruments, list)
    assert len(instruments) > 0
    assert "ticker" in instruments[0]


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
            validate_timeseries(json["prices"])
            return
    pytest.skip("No instrument with available price data")


def test_instrument_detail_not_found():
    groups = client.get("/groups").json()
    slug = groups[0]["slug"]
    resp = client.get(f"/portfolio-group/{slug}/instrument/FAKETICK")
    assert resp.status_code == 404


def test_yahoo_timeseries_html():
    ticker = "AAPL"
    resp = client.get(f"/timeseries/html?ticker={ticker}&period=1y&interval=1d")
    assert resp.status_code == 200
    html = resp.text.lower()
    assert "<html" in html and "<table" in html
    assert ticker.lower() in html


# @pytest.mark.parametrize("format", ["html", "json", "csv"])
# def test_ft_timeseries(format):
#     ticker = "GB00B45Q9038:GBP"
#     resp = client.get(f"/timeseries/ft?ticker={ticker}&period=1y&interval=1d&format={format}")
#     if resp.status_code == 404:
#         pytest.skip("FT timeseries data not available")
#
#     assert resp.status_code == 200
#
#     if format == "json":
#         data = resp.json()
#         validate_timeseries(data)
#
#     elif format == "csv":
#         df = pd.read_csv(StringIO(resp.text))
#         assert not df.empty
#         assert "date" in df.columns and "close" in df.columns
#         assert df["date"].is_monotonic_increasing
#
#     elif format == "html":
#         html = resp.text.lower()
#         assert "<table" in html and "ft time series" in html
