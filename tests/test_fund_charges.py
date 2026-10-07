"""Fund ongoing charges are read from metadata, unknown is never 0% (#7834)."""

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.fund_charges import ongoing_charge_pct
from backend.config import config


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"ongoing_charge_pct": 0.22}, 0.22),
        ({"ongoing_charge_pct": "0.15"}, 0.15),
        ({"ongoing_charge_pct": 0}, 0.0),
        ({}, None),
        (None, None),
        ({"ongoing_charge_pct": None}, None),
        ({"ongoing_charge_pct": ""}, None),
        ({"ongoing_charge_pct": "n/a"}, None),
        ({"ongoing_charge_pct": True}, None),
        ({"ongoing_charge_pct": -0.1}, None),
        ({"ongoing_charge_pct": 22}, None),
        ({"ongoing_charge_pct": float("nan")}, None),
    ],
)
def test_ongoing_charge_pct(meta, expected):
    assert ongoing_charge_pct(meta) == expected


def test_enrich_holding_carries_charge_and_unknown(monkeypatch):
    from backend.common import holding_utils
    from backend.common.holding_utils import enrich_holding

    metas = {"FUND.L": {"name": "Fund", "ongoing_charge_pct": 0.12}, "NOFEE.L": {"name": "No fee data"}}
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda t: metas.get(t, {}))
    known = enrich_holding({"ticker": "FUND.L", "units": 0}, date.today(), {}, {})
    unknown = enrich_holding({"ticker": "NOFEE.L", "units": 0}, date.today(), {}, {})
    assert known["ongoing_charge_pct"] == 0.12
    assert unknown["ongoing_charge_pct"] is None


def _instrument_json(monkeypatch, file_meta):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = pd.DataFrame(
        {"Date": pd.date_range("2020-01-01", periods=2, freq="D"), "Close": [10.0, 11.0], "Close_gbp": [10.0, 11.0]}
    )
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df),
        patch("backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}),
        patch("backend.routes.instrument.get_instrument_meta", return_value=file_meta),
        patch("backend.routes.instrument.list_portfolios", return_value=[]),
    ):
        client = TestClient(app)
        token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})
        resp = client.get("/instrument?ticker=ABC.L&days=0&format=json")
    assert resp.status_code == 200
    return resp.json()


def test_instrument_json_includes_ongoing_charge(monkeypatch):
    body = _instrument_json(monkeypatch, {"ongoing_charge_pct": 0.07})
    assert body["ongoing_charge_pct"] == 0.07


def test_instrument_json_reports_unknown_charge_as_null(monkeypatch):
    body = _instrument_json(monkeypatch, {"name": "ABC"})
    assert body["ongoing_charge_pct"] is None
