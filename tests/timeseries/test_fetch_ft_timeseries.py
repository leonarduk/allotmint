from datetime import date
from unittest.mock import patch
from bs4 import BeautifulSoup as RealBeautifulSoup

from backend.timeseries.fetch_ft_timeseries import (
    _build_ft_ticker,
    fetch_ft_timeseries,
    fetch_ft_timeseries_range,
)


def test_build_ft_ticker_valid_isin():
    assert _build_ft_ticker("GB0000000001") == "GB0000000001:GBP"


def test_build_ft_ticker_non_isin_returns_none():
    assert _build_ft_ticker("AAPL") is None


def test_fetch_ft_timeseries_range_success():
    html = """
    <table class="mod-ui-table">
    <thead>
    <tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr>
    </thead>
    <tbody>
    <tr><td><span>Monday, January 01, 2024</span></td><td>1</td><td>2</td><td>0</td><td>1.5</td><td>100</td></tr>
    <tr><td><span>Tuesday, January 02, 2024</span></td><td>1.2</td><td>2.2</td><td>0.2</td><td>1.6</td><td>200</td></tr>
    </tbody>
    </table>
    """

    class FakeElement:
        def __init__(self, html):
            self.html = html

        def get_attribute(self, name):
            assert name == "outerHTML"
            return self.html

        def click(self):
            pass

    class FakeDriver:
        def __init__(self, html):
            self.html = html

        def get(self, url):
            self.url = url

        def find_element(self, by, selector):
            if selector == "table.mod-ui-table":
                return FakeElement(self.html)
            if selector == "button.js-accept-all-cookies":
                raise Exception("no cookie banner")
            raise Exception("unexpected selector")

        def quit(self):
            pass

    with patch("backend.timeseries.fetch_ft_timeseries.init_driver", return_value=FakeDriver(html)), \
        patch("backend.timeseries.fetch_ft_timeseries.WebDriverWait") as MockWait, \
        patch("backend.timeseries.fetch_ft_timeseries.BeautifulSoup", wraps=RealBeautifulSoup):
        MockWait.return_value.until.return_value = True
        df = fetch_ft_timeseries_range("TEST:GBP", date(2024, 1, 1), date(2024, 1, 2))

    assert not df.empty
    assert list(df["Ticker"]) == ["TEST:GBP", "TEST:GBP"]
    assert (df["Source"] == "FT").all()


def test_fetch_ft_timeseries_range_failure():
    class FailingDriver:
        def get(self, url):
            raise Exception("boom")

        def quit(self):
            pass

    with patch("backend.timeseries.fetch_ft_timeseries.init_driver", return_value=FailingDriver()), \
        patch("backend.timeseries.fetch_ft_timeseries.WebDriverWait"), \
        patch("backend.timeseries.fetch_ft_timeseries.BeautifulSoup"):
        df = fetch_ft_timeseries_range("TEST:GBP", date(2024, 1, 1), date(2024, 1, 2))

    assert df.empty


def test_fetch_ft_timeseries_non_isin_returns_empty_df():
    df = fetch_ft_timeseries("AAPL")
    assert df.empty
