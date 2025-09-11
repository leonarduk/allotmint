from datetime import date

from backend.timeseries.fetch_ft_timeseries import (
    _build_ft_ticker,
    fetch_ft_timeseries,
    fetch_ft_timeseries_range,
)
from backend.utils.timeseries_helpers import STANDARD_COLUMNS


def test_build_ft_ticker_valid_isin():
    assert _build_ft_ticker("GB0000000001") == "GB0000000001:GBP"


def test_build_ft_ticker_non_isin_returns_none():
    assert _build_ft_ticker("AAPL") is None


def test_fetch_ft_timeseries_range_no_cookie_banner(monkeypatch):
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
        def __init__(self, html: str):
            self.html = html

        def get_attribute(self, name: str) -> str:
            assert name == "outerHTML"
            return self.html

        def click(self):
            pass

    class FakeDriver:
        def __init__(self):
            self.quit_called = False

        def get(self, url: str):
            self.url = url

        def find_element(self, by, selector):
            if selector == "button.js-accept-all-cookies":
                raise Exception("no cookie banner")
            if selector == "table.mod-ui-table":
                return FakeElement(html)
            raise Exception("unexpected selector")

        def quit(self):
            self.quit_called = True

    driver = FakeDriver()

    class FakeWait:
        def __init__(self, driver, timeout):
            pass

        def until(self, condition):
            return True

    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.init_driver", lambda *a, **k: driver)
    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.WebDriverWait", FakeWait)

    df = fetch_ft_timeseries_range("TEST:GBP", date(2024, 1, 1), date(2024, 1, 2))

    assert not df.empty
    assert list(df.columns) == STANDARD_COLUMNS
    assert driver.quit_called


def test_fetch_ft_timeseries_range_find_element_failure(monkeypatch):
    class FailingDriver:
        def __init__(self):
            self.quit_called = False

        def get(self, url: str):
            self.url = url

        def find_element(self, by, selector):
            raise Exception("boom")

        def quit(self):
            self.quit_called = True

    driver = FailingDriver()

    class FakeWait:
        def __init__(self, driver, timeout):
            pass

        def until(self, condition):
            return True

    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.init_driver", lambda *a, **k: driver)
    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.WebDriverWait", FakeWait)

    df = fetch_ft_timeseries_range("TEST:GBP", date(2024, 1, 1), date(2024, 1, 2))

    assert df.empty
    assert driver.quit_called


def test_fetch_ft_timeseries_non_isin_returns_empty_df():
    df = fetch_ft_timeseries("AAPL")
    assert df.empty
