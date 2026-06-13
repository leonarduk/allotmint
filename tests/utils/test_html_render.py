from pathlib import Path
import numpy as np
import pandas as pd
from lxml import html

from backend.utils.html_render import render_timeseries_html


ROOT = Path(__file__).resolve().parent.parent.parent


def test_render_timeseries_html():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "Open": [1.2345, 2.3456],
            "High": [3.1234, 4.2345],
            "Low": [1.1234, 2.2345],
            "Close": [2.2345, 3.3456],
            "Volume": [12345, np.nan],
            "Ticker": ["ABC", "ABC"],
            "Source": ["Test", "Test"],
        }
    )

    response = render_timeseries_html(df, "Title", "Sub")
    html_str = response.body.decode()

    tree = html.fromstring(html_str)

    # Title and subtitle
    h2 = tree.xpath("//h2")[0]
    assert h2.text == "Title"
    assert h2.xpath("small/text()") == ["Sub"]

    # Table classes
    table = tree.xpath("//table")[0]
    classes = set(table.attrib.get("class", "").split())
    assert {"table", "table-striped", "text-center"}.issubset(classes)

    # Table data
    rows = table.xpath(".//tr")
    first = [td.text for td in rows[1].xpath(".//td")]
    second = [td.text for td in rows[2].xpath(".//td")]

    assert first[1:5] == ["1.23", "3.12", "1.12", "2.23"]
    assert second[1:5] == ["2.35", "4.23", "2.23", "3.35"]

    # Volume formatting
    assert first[5] == "12,345"
    assert (second[5] or "") == ""

    # Snapshot for regression detection
    expected = (ROOT / "tests/snapshots/render_timeseries.html").read_text()
    assert html_str == expected


def test_render_timeseries_html_escapes_title_and_subtitle():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01"]),
            "Open": [1.0],
            "High": [1.0],
            "Low": [1.0],
            "Close": [1.0],
            "Volume": [1],
            "Ticker": ["ABC"],
            "Source": ["Test"],
        }
    )

    response = render_timeseries_html(df, "Title <script>", "Sub <b>")
    html_str = response.body.decode()

    assert "&lt;script&gt;" in html_str
    assert "<script>" not in html_str
    assert "&lt;b&gt;" in html_str
    assert "<b>" not in html_str


def test_render_timeseries_html_escapes_cell_values():
    """Verify dataframe cell values containing XSS payloads are HTML-escaped.

    This test confirms that ``escape=True`` on ``df.to_html()`` (the fix for
    CodeQL alert py/reflective-xss, #4136) protects the HTML table content
    from injection through user-controlled ticker/exchange data.
    """
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01"]),
            "Open": [1.0],
            "High": [1.0],
            "Low": [1.0],
            "Close": [1.0],
            "Volume": [1],
            "Ticker": ['<script>alert("XSS")</script>'],
            "Source": ["<img src=x onerror=alert(1)>"],
        }
    )

    response = render_timeseries_html(df, "Title", "Sub")
    html_str = response.body.decode()

    # Critical HTML structural characters (&, <, >) must be escaped.
    # df.to_html(escape=True) converts these to entities, preventing any
    # injection of executable HTML/JS — the remaining attribute text is
    # inert inside the escaped tag body.
    assert "&lt;script&gt;" in html_str
    assert "<script>" not in html_str
    assert "&lt;img" in html_str
    assert "<img" not in html_str

    # Verify the raw HTML source has properly encoded entities.
    # (lxml's td.text decodes entities back, so we check the raw string.)
    assert "&lt;script&gt;alert" in html_str
    assert "&lt;/script&gt;" in html_str
    assert "&lt;img src=x onerror=alert(1)&gt;" in html_str

    # Also confirm the cell content is still readable text (entities decoded
    # by the browser/lxml into harmless display text, not executable HTML).
    tree = html.fromstring(html_str)
    rows = tree.xpath(".//tr")
    cells = [td.text for td in rows[1].xpath(".//td")]
    ticker_idx = 6  # Ticker is the 7th column (0-indexed)
    source_idx = 7  # Source is the 8th column
    assert 'alert("XSS")' in cells[ticker_idx]
    assert "alert(1)" in cells[source_idx]
