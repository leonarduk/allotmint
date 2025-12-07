import pandas as pd

from backend.utils.html_render import render_timeseries_html


def _df():
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01"]),
            "Open": [1.2345],
            "High": [2.3456],
            "Low": [1.1234],
            "Close": [2.2345],
            "Volume": [12345],
            "Ticker": ["ABC"],
            "Source": ["Test"],
        }
    )


def test_render_timeseries_html_basic():
    response = render_timeseries_html(_df(), "Title", "Sub")
    html = response.body.decode()
    assert "Title" in html and "Sub" in html
    assert "12,345" in html
    assert "1.23" in html


def test_render_timeseries_html_escapes():
    response = render_timeseries_html(_df(), "T<script>", "S&b")
    html = response.body.decode()
    assert "&lt;script&gt;" in html
    assert "S&amp;b" in html
