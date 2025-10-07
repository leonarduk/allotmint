import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fastapi.responses import HTMLResponse

from backend.utils import timeseries_helpers as th


def test_apply_scaling_scales_numeric_columns():
    df = pd.DataFrame(
        {
            "Open": [1, 2],
            "high": [3, 4],
            "Low": [5, 6],
            "close": [7, 8],
            "volume": [10, 20],
        }
    )

    scaled = th.apply_scaling(df, scale=2.5, scale_volume=True)

    assert scaled["Open"].tolist() == [2.5, 5.0]
    assert scaled["high"].tolist() == [7.5, 10.0]
    assert scaled["Low"].tolist() == [12.5, 15.0]
    assert scaled["close"].tolist() == [17.5, 20.0]
    assert scaled["volume"].tolist() == [25.0, 50.0]
    # original frame left untouched when scaling occurs
    assert df["Open"].tolist() == [1, 2]


@pytest.mark.parametrize("scale", [None, 1])
def test_apply_scaling_noop(scale):
    df = pd.DataFrame({"Open": [1.0]})

    result = th.apply_scaling(df, scale=scale)

    assert result is df


def test_get_scaling_override_prefers_requested(tmp_path, monkeypatch):
    assert (
        th.get_scaling_override("ABC.L", "L", requested_scaling=3.0)
        == 3.0
    )


def test_get_scaling_override_reads_override_file(tmp_path, monkeypatch):
    overrides = {"L": {"ABC.L": "1.25"}, "*": {"*": 5}}
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "scaling_overrides.json").write_text(json.dumps(overrides))

    monkeypatch.setattr(th.config, "repo_root", tmp_path)

    value = th.get_scaling_override("ABC.L", "L", requested_scaling=None)

    assert value == pytest.approx(1.25)


def test_get_scaling_override_currency_detection(monkeypatch):
    monkeypatch.setattr(th.config, "repo_root", Path("/nonexistent"))

    from backend.common import instruments
    from backend.common import portfolio_utils

    monkeypatch.setattr(instruments, "get_instrument_meta", lambda ticker: {"currency": "GBp"})
    monkeypatch.setattr(
        portfolio_utils,
        "get_security_meta",
        lambda ticker: {"quote": {"currency": "usd"}},
    )

    value = th.get_scaling_override("XYZ.L", "L", requested_scaling=None)

    assert value == pytest.approx(0.01)


def test_get_scaling_override_falls_back_to_security_meta(monkeypatch):
    monkeypatch.setattr(th.config, "repo_root", Path("/nonexistent"))

    from backend.common import instruments
    from backend.common import portfolio_utils

    monkeypatch.setattr(instruments, "get_instrument_meta", lambda ticker: {})
    monkeypatch.setattr(
        portfolio_utils,
        "get_security_meta",
        lambda ticker: {"price": {"Currency": "USD"}},
    )

    value = th.get_scaling_override("XYZ.N", "N", requested_scaling=None)

    assert value == pytest.approx(1.0)


def test_handle_timeseries_response_empty_df():
    df = pd.DataFrame()

    response = th.handle_timeseries_response(
        df, format="html", title="Title", subtitle="Sub"
    )

    assert response.status_code == 404
    assert response.body == b"<h1>No data found</h1>"


def test_handle_timeseries_response_json_includes_metadata():
    df = pd.DataFrame([{ "Close": 10 }])

    response = th.handle_timeseries_response(
        df,
        format="json",
        title="Title",
        subtitle="Sub",
        metadata={"ticker": "ABC"},
    )

    payload = json.loads(response.body)
    assert payload["ticker"] == "ABC"
    assert payload["prices"] == [{"Close": 10}]


def test_handle_timeseries_response_csv(tmp_path):
    df = pd.DataFrame([
        {"Date": "2024-01-01", "Close": 10},
        {"Date": "2024-01-02", "Close": 11},
    ])

    response = th.handle_timeseries_response(
        df, format="csv", title="Title", subtitle="Sub"
    )

    assert response.media_type == "text/csv"
    assert "Date,Close" in response.body.decode()


def test_handle_timeseries_response_html(monkeypatch):
    marker = HTMLResponse("ok", status_code=202)
    monkeypatch.setattr(
        th,
        "render_timeseries_html",
        lambda df, title, subtitle: marker,
    )
    df = pd.DataFrame([{ "Close": 10 }])

    response = th.handle_timeseries_response(
        df, format="htmlish", title="Title", subtitle="Sub"
    )

    assert response is marker


@pytest.mark.parametrize(
    "input_date, forward, expected",
    [
        (date(2024, 1, 6), True, date(2024, 1, 8)),   # Saturday -> Monday
        (date(2024, 1, 7), False, date(2024, 1, 5)),  # Sunday -> Friday
        (date(2024, 1, 8), True, date(2024, 1, 8)),   # Weekday unchanged
    ],
)
def test_nearest_weekday(input_date, forward, expected):
    assert th._nearest_weekday(input_date, forward) == expected


@pytest.mark.parametrize(
    "ticker, expected",
    [
        ("US0378331005", True),
        ("AAPL", False),
        ("GB0002634946.L", True),
        ("INVALID@@", False),
    ],
)
def test_is_isin(ticker, expected):
    assert th._is_isin(ticker) is expected
