from datetime import date
from types import SimpleNamespace

from backend.timeseries.fetch_ft_timeseries import (
    _build_ft_ticker,
    fetch_ft_timeseries,
    fetch_ft_timeseries_range,
)
from backend.utils.timeseries_helpers import STANDARD_COLUMNS


def test_build_ft_ticker_valid_isin():
    assert _build_ft_ticker("GB0000000001") == "GB0000000001:GBP"


def test_build_ft_ticker_non_isin_returns_none():
    assert _build_ft_ticker("PFE") is None


def test_fetch_ft_timeseries_range_cookie_banner(monkeypatch):
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

    class FakeTableElement:
        def __init__(self, html: str):
            self.html = html

        def get_attribute(self, name: str) -> str:
            assert name == "outerHTML"
            return self.html

    class FakeCookieElement:
        def __init__(self, driver):
            self.driver = driver

        def click(self):
            self.driver.cookie_clicked = True

    class FakeChrome:
        def __init__(self):
            self.url = None
            self.quit_called = False
            self.cookie_clicked = False

        def get(self, url: str):
            self.url = url

        def find_element(self, by, selector):
            if selector == "button.js-accept-all-cookies":
                return FakeCookieElement(self)
            if selector == "table.mod-ui-table":
                return FakeTableElement(html)
            raise Exception("unexpected selector")

        def quit(self):
            self.quit_called = True

    driver = FakeChrome()

    class FakeWait:
        def __init__(self, driver, timeout):
            pass

        def until(self, condition):
            return True

    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.webdriver.Chrome", lambda *a, **k: driver)
    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.WebDriverWait", FakeWait)
    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.time.sleep", lambda *a, **k: None)

    df = fetch_ft_timeseries_range("TEST:GBP", date(2024, 1, 1), date(2024, 1, 2))

    assert driver.cookie_clicked
    assert not df.empty
    assert list(df.columns) == STANDARD_COLUMNS
    assert driver.quit_called


def test_fetch_ft_timeseries_range_find_element_failure(monkeypatch):
    class FailingChrome:
        def __init__(self):
            self.url = None
            self.quit_called = False

        def get(self, url: str):
            self.url = url

        def find_element(self, by, selector):
            raise Exception("boom")

        def quit(self):
            self.quit_called = True

    driver = FailingChrome()

    class FakeWait:
        def __init__(self, driver, timeout):
            pass

        def until(self, condition):
            return True

    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.webdriver.Chrome", lambda *a, **k: driver)
    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.WebDriverWait", FakeWait)

    df = fetch_ft_timeseries_range("TEST:GBP", date(2024, 1, 1), date(2024, 1, 2))

    assert df.empty
    assert list(df.columns) == STANDARD_COLUMNS
    assert driver.quit_called


def test_fetch_ft_timeseries_non_isin_returns_empty_df():
    df = fetch_ft_timeseries("PFE")
    assert df.empty


def _fetch_ft_rows(monkeypatch, rows_html: str):
    html = (
        '<table class="mod-ui-table"><thead><tr><th>Date</th><th>Open</th><th>High</th>'
        f"<th>Low</th><th>Close</th><th>Volume</th></tr></thead><tbody>{rows_html}</tbody></table>"
    )

    class FakeChrome:
        def get(self, url):
            pass

        def find_element(self, by, selector):
            if selector == "table.mod-ui-table":
                return SimpleNamespace(get_attribute=lambda name: html)
            raise Exception("no cookie banner")

        def quit(self):
            pass

    class FakeWait:
        def __init__(self, driver, timeout):
            pass

        def until(self, condition):
            return True

    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.webdriver.Chrome", lambda *a, **k: FakeChrome())
    monkeypatch.setattr("backend.timeseries.fetch_ft_timeseries.WebDriverWait", FakeWait)
    return fetch_ft_timeseries_range("TEST:GBP", date(2026, 9, 30), date(2026, 9, 30))


def test_fetch_ft_keeps_sub_one_precision(monkeypatch):
    """A sub-1 quote keeps its 4th decimal rather than a 2 dp tick (#9456)."""
    df = _fetch_ft_rows(
        monkeypatch,
        "<tr><td><span>Wednesday, September 30, 2026</span></td>"
        "<td>0.9399</td><td>0.9449</td><td>0.9387</td><td>0.9416</td><td>12345</td></tr>",
    )

    assert df[["Open", "High", "Low", "Close"]].iloc[0].tolist() == [0.9399, 0.9449, 0.9387, 0.9416]
    assert df["Close"].dtype == "float64"
    assert df["Volume"].iloc[0] == 12345
    assert df["Ticker"].iloc[0] == "TEST:GBP"


def test_fetch_ft_keeps_pence_scale_precision(monkeypatch):
    """A >1000p close keeps its decimal pence (six significant figures)."""
    df = _fetch_ft_rows(
        monkeypatch,
        "<tr><td><span>Wednesday, September 30, 2026</span></td>"
        "<td>4567.25</td><td>4580.5</td><td>4551</td><td>4573.5</td><td>987654321</td></tr>",
    )

    assert df[["Open", "High", "Low", "Close"]].iloc[0].tolist() == [4567.25, 4580.5, 4551.0, 4573.5]
    assert df["Volume"].iloc[0] == 987654321
