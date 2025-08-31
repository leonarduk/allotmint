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
