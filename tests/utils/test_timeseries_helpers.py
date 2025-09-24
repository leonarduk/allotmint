import builtins
import datetime as dt
import json
from types import SimpleNamespace

import pandas as pd

import backend.utils.timeseries_helpers as th


def test_apply_scaling_basic():
    df = pd.DataFrame({"Open": [1], "Close": [2], "Volume": [3]})
    scaled = th.apply_scaling(df, 2, scale_volume=True)
    assert list(scaled["Open"]) == [2]
    assert list(scaled["Close"]) == [4]
    assert list(scaled["Volume"]) == [6]


def test_apply_scaling_no_scale_returns_same_object():
    df = pd.DataFrame({"Open": [1]})
    same = th.apply_scaling(df, 1)
    assert same is df


def test_get_scaling_override_requested():
    assert th.get_scaling_override("T", "L", 3.0) == 3.0


def test_get_scaling_override_from_json():
    assert th.get_scaling_override("GAMA", "L", None) == 0.01
    assert th.get_scaling_override("ADM", "L", None) == 0.1


def test_get_scaling_override_missing_file(monkeypatch):
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    assert th.get_scaling_override("T", "X", None) == 1.0


def test_get_scaling_override_nested_currency(monkeypatch):
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta",
        lambda symbol: {"price": {"currency": "GBp"}},
    )

    assert th.get_scaling_override("TEST", "L", None) == 0.01


def test_get_scaling_override_security_meta_fallback(monkeypatch):
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta",
        lambda symbol: {},
    )
    monkeypatch.setattr(
        "backend.common.portfolio_utils.get_security_meta",
        lambda symbol: {"currency": "USD"},
    )

    assert th.get_scaling_override("TEST", "NYSE", None) == 1.0


def test_handle_timeseries_response_variants(monkeypatch):
    df = pd.DataFrame({"Date": ["2024-01-01"], "Open": [1], "Close": [1], "High": [1], "Low": [1], "Volume": [0]})

    # JSON
    resp = th.handle_timeseries_response(df, "json", "t", "s", {"meta": 1})
    body = json.loads(resp.body)
    assert body["meta"] == 1
    assert body["prices"][0]["Open"] == 1

    # CSV
    resp_csv = th.handle_timeseries_response(df, "csv", "t", "s")
    assert resp_csv.media_type == "text/csv"
    assert "Open" in resp_csv.body.decode()

    # HTML branch
    monkeypatch.setattr(th, "render_timeseries_html", lambda df, t, s: "HTML")
    resp_html = th.handle_timeseries_response(df, "html", "t", "s")
    assert resp_html == "HTML"

    # Empty DataFrame -> 404
    resp_empty = th.handle_timeseries_response(pd.DataFrame(), "json", "t", "s")
    assert resp_empty.status_code == 404

    # JSON without metadata
    resp_plain = th.handle_timeseries_response(df, "json", "t", "s")
    body_plain = json.loads(resp_plain.body)
    assert body_plain[0]["Open"] == 1


def test_get_scaling_override_bad_json(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "scaling_overrides.json").write_text("not json")
    monkeypatch.setattr(th, "config", SimpleNamespace(repo_root=tmp_path))
    assert th.get_scaling_override("T", "X", None) == 1.0


def test_get_scaling_override_invalid_value(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "scaling_overrides.json").write_text('{"*": {"*": "bad"}}')
    monkeypatch.setattr(th, "config", SimpleNamespace(repo_root=tmp_path))
    assert th.get_scaling_override("T", "X", None) == 1.0


def test_nearest_weekday():
    sat = dt.date(2024, 1, 6)
    sun = dt.date(2024, 1, 7)
    assert th._nearest_weekday(sat, True) == dt.date(2024, 1, 8)
    assert th._nearest_weekday(sat, False) == dt.date(2024, 1, 5)
    assert th._nearest_weekday(sun, False) == dt.date(2024, 1, 5)


def test_is_isin():
    assert th._is_isin("US0378331005")
    assert not th._is_isin("PFE")
