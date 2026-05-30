import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.config import config

# ---- Helper utilities -----------------------------------------------------


def _client_with_df(monkeypatch, df):
    """Return TestClient with ``load_meta_timeseries_range`` patched."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "offline_mode", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.routes.timeseries_meta as ts_meta

    monkeypatch.setattr(
        ts_meta, "load_meta_timeseries_range", lambda *a, **k: df.copy()
    )
    monkeypatch.setattr(ts_meta.pd, "to_datetime", lambda x: x)

    from backend.app import create_app

    app = create_app()
    return TestClient(app)


# ---- _resolve_ticker_exchange tests ---------------------------------------


def test_resolve_with_provided_exchange():
    import backend.routes.timeseries_meta as ts_meta

    sym, ex = ts_meta._resolve_ticker_exchange("abc", "l")
    assert sym == "ABC"
    assert ex == "L"


def test_resolve_with_inferred_exchange(monkeypatch):
    import backend.routes.timeseries_meta as ts_meta

    monkeypatch.setattr(
        ts_meta.instrument_api,
        "_resolve_full_ticker",
        lambda t, latest: ("XYZ", "L"),
    )
    sym, ex = ts_meta._resolve_ticker_exchange("xyz", None)
    assert (sym, ex) == ("XYZ", "L")


def test_resolve_missing_ticker_error():
    import backend.routes.timeseries_meta as ts_meta

    with pytest.raises(HTTPException):
        ts_meta._resolve_ticker_exchange("", "L")


def test_resolve_cannot_infer_exchange(monkeypatch):
    import backend.routes.timeseries_meta as ts_meta

    monkeypatch.setattr(
        ts_meta.instrument_api, "_resolve_full_ticker", lambda t, latest: None
    )
    with pytest.raises(HTTPException):
        ts_meta._resolve_ticker_exchange("xyz", None)


def test_resolve_inferred_path_trusts_internal_data(monkeypatch):
    """The regex allowlist guards user-supplied paths only.

    When _resolve_full_ticker returns a segment containing characters outside
    [A-Z0-9_-] (e.g. a dot in an exchange code returned by an internal data
    source), the route must NOT reject it with HTTP 400.  The guard applies
    only to user-controlled input so valid portfolio entries never cause false
    production errors.
    """
    import backend.routes.timeseries_meta as ts_meta

    monkeypatch.setattr(
        ts_meta.instrument_api,
        "_resolve_full_ticker",
        lambda t, latest: ("AAAA", "XLON.G"),  # "." is outside the user-input allowlist
    )
    # Must succeed — internally-resolved tickers bypass the regex.
    sym, ex = ts_meta._resolve_ticker_exchange("aaaa", None)
    assert sym == "AAAA"
    assert ex == "XLON.G"


def test_resolve_dotted_ticker_no_exchange():
    """Covers the 'elif . in t' branch: ticker='ABC.L', exchange=None."""
    import backend.routes.timeseries_meta as ts_meta

    sym, ex = ts_meta._resolve_ticker_exchange("abc.l", None)
    assert sym == "ABC"
    assert ex == "L"


@pytest.mark.parametrize("ticker_input,exchange_input", [
    ("<script>alert(1)</script>", "L"),
    ("ABC", "<img src=x onerror=alert(1)>"),
    ("ABC&foo=bar", "L"),
    ("ABC\"onload=x", "L"),
])
def test_resolve_rejects_unsafe_ticker_exchange(ticker_input, exchange_input):
    """User-supplied exchange path rejects payloads that fail the regex allowlist."""
    import backend.routes.timeseries_meta as ts_meta

    with pytest.raises(HTTPException) as exc_info:
        ts_meta._resolve_ticker_exchange(ticker_input, exchange_input)
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize("bad_dotted_ticker", [
    "<script>.L",      # XSS payload in the sym segment
    "ABC.<img>",       # XSS payload in the exchange segment
    "ABC&foo=bar.L",   # injection attempt in the sym segment
])
def test_resolve_rejects_unsafe_dotted_ticker_no_exchange(bad_dotted_ticker):
    """The 'if . in t' branch validates sym/ex derived from the dotted ticker.

    Covers the case where exchange=None and the ticker contains a dot so the
    exchange is inferred by splitting — both segments are still user-controlled
    and must be rejected if they fail _TICKER_SEGMENT_RE.
    """
    import backend.routes.timeseries_meta as ts_meta

    with pytest.raises(HTTPException) as exc_info:
        ts_meta._resolve_ticker_exchange(bad_dotted_ticker, None)
    assert exc_info.value.status_code == 400


def test_timeseries_meta_json_rejects_xss_ticker(monkeypatch):
    df = _sample_df()
    client = _client_with_df(monkeypatch, df)
    resp = client.get(
        "/timeseries/meta?ticker=%3Cscript%3Ealert(1)%3C%2Fscript%3E&exchange=L&format=json"
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("ticker,exchange", [
    ("BRK_B", "NYSE"),   # underscore in ticker symbol — allowed by widened regex
    ("FUND_ETF", "L"),   # underscore in fund identifier — allowed
])
def test_resolve_accepts_underscore_ticker(ticker, exchange):
    """Underscores are explicitly permitted (some providers use them as separators)."""
    import backend.routes.timeseries_meta as ts_meta

    sym, ex = ts_meta._resolve_ticker_exchange(ticker, exchange)
    assert sym == ticker.upper()
    assert ex == exchange.upper()


@pytest.mark.parametrize("ticker,exchange", [
    ("A" * 51, "L"),   # ticker segment exceeds 50-char limit
    ("AAPL", "X" * 51),   # exchange code exceeds 50-char limit
])
def test_resolve_rejects_oversized_segments(ticker, exchange):
    """Segments longer than 50 characters are rejected."""
    import backend.routes.timeseries_meta as ts_meta

    with pytest.raises(HTTPException) as exc_info:
        ts_meta._resolve_ticker_exchange(ticker, exchange)
    assert exc_info.value.status_code == 400


# ---- /timeseries/meta route tests -----------------------------------------


def _sample_df():
    return pd.DataFrame(
        [
            {
                "Date": "2024-01-01",
                "Open": 1.0,
                "High": 2.0,
                "Low": 0.5,
                "Close": 1.5,
                "Volume": 100,
            }
        ]
    )


@pytest.mark.parametrize("fmt", ["json", "csv", "html"])
def test_timeseries_meta_formats_with_scaling(fmt, monkeypatch):
    df = _sample_df()
    client = _client_with_df(monkeypatch, df)

    resp = client.get(
        f"/timeseries/meta?ticker=ABC&exchange=L&format={fmt}&scaling=2"
    )
    assert resp.status_code == 200

    if fmt == "json":
        data = resp.json()
        assert data["scaling"] == 2
        assert data["prices"][0]["Close"] == 3.0
    elif fmt == "csv":
        assert "Date,Open,High,Low,Close,Volume" in resp.text
        assert "3.0" in resp.text
    else:  # html
        assert "<table" in resp.text
        # Scaling is shown in the Bootstrap subtitle produced by render_timeseries_html
        assert "scaling: 2.0x" in resp.text
        assert "3.0" in resp.text


# ---- /timeseries/html route tests -----------------------------------------


def _html_client(monkeypatch, yahoo_result):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "offline_mode", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.routes.timeseries_meta as ts_meta

    def fake_fetch(*_args, **_kwargs):
        if isinstance(yahoo_result, Exception):
            raise yahoo_result
        return yahoo_result.copy()

    monkeypatch.setattr(ts_meta.fetch_timeseries, "fetch_yahoo_timeseries", fake_fetch)
    monkeypatch.setattr(ts_meta, "get_scaling_override", lambda *a, **k: 1)
    monkeypatch.setattr(ts_meta, "apply_scaling", lambda df, scale: df)

    from backend.app import create_app

    app = create_app()
    return TestClient(app)


def test_timeseries_html_success(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "Date": "2024-01-01",
                "Open": 1.0,
                "High": 1.5,
                "Low": 0.5,
                "Close": 1.2,
                "Volume": 100,
            }
        ]
    )
    client = _html_client(monkeypatch, df)
    resp = client.get("/timeseries/html?ticker=ABC&period=1y&interval=1d")
    assert resp.status_code == 200
    assert "ABC Price History" in resp.text
    assert "1.20" in resp.text


def test_timeseries_html_fallback(monkeypatch):
    client = _html_client(monkeypatch, Exception("boom"))
    resp = client.get("/timeseries/html?ticker=ABC&period=1y&interval=1d")
    assert resp.status_code == 200
    assert "ABC Price History" in resp.text
    assert "0.00" in resp.text


# ---- /timeseries/meta date-range parameter tests --------------------------


def _multi_day_df():
    rows = [
        {"Date": "2024-01-01", "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100},
        {"Date": "2024-01-02", "Open": 2.0, "High": 3.0, "Low": 1.0, "Close": 2.5, "Volume": 200},
        {"Date": "2024-01-03", "Open": 3.0, "High": 4.0, "Low": 2.0, "Close": 3.5, "Volume": 300},
    ]
    return pd.DataFrame(rows)


def test_explicit_start_and_end_date(monkeypatch):
    """Both dates supplied: response reflects the provided bounds."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json"
        "&start_date=2024-01-01&end_date=2024-01-03"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["from"] == "2024-01-01"
    assert data["to"] == "2024-01-03"


def test_open_start_only_end_date(monkeypatch):
    """Only end_date supplied: response uses end_date and days-derived start."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json&end_date=2024-01-03"
    )
    assert resp.status_code == 200
    assert resp.json()["to"] == "2024-01-03"


def test_open_end_only_start_date(monkeypatch):
    """Only start_date supplied: response uses start_date and yesterday as end."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json&start_date=2024-01-01"
    )
    assert resp.status_code == 200
    assert resp.json()["from"] == "2024-01-01"


def test_neither_date_param_uses_days(monkeypatch):
    """No date params: existing days-based behaviour is preserved (regression guard)."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get("/timeseries/meta?ticker=ABC&exchange=L&format=json&days=365")
    assert resp.status_code == 200
    data = resp.json()
    assert "from" in data and "to" in data


def test_invalid_range_returns_422(monkeypatch):
    """start_date after end_date must return HTTP 422 (FastAPI validation convention)."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json"
        "&start_date=2024-01-10&end_date=2024-01-01"
    )
    assert resp.status_code == 422


def test_single_day_range(monkeypatch):
    """start_date == end_date is a valid single-day window; must not raise."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json"
        "&start_date=2024-01-02&end_date=2024-01-02"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["from"] == "2024-01-02"
    assert data["to"] == "2024-01-02"


def test_malformed_date_returns_4xx(monkeypatch):
    """A non-ISO date string must be rejected with a 4xx error.

    The app's custom exception handler maps FastAPI's RequestValidationError
    to 400 rather than the default 422, so either status is accepted here.
    """
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json&start_date=not-a-date"
    )
    assert resp.status_code in (400, 422)


def test_html_shows_date_range(monkeypatch):
    """HTML output subtitle must contain the resolved date range."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=html"
        "&start_date=2024-01-01&end_date=2024-01-03"
    )
    assert resp.status_code == 200
    assert "2024-01-01" in resp.text
    assert "2024-01-03" in resp.text
    assert "<table" in resp.text


def test_csv_with_date_range(monkeypatch):
    """CSV output must work correctly when explicit date params are supplied.

    Regression guard for the elif→if refactor on the CSV branch: the JSON
    path returns early, so the CSV `if` must still be reached independently.
    """
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=csv"
        "&start_date=2024-01-01&end_date=2024-01-03"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "Date,Open,High,Low,Close,Volume" in resp.text
    assert "2024-01-01" in resp.text


def test_explicit_start_date_ignores_days(monkeypatch):
    """When start_date is explicit, the days param is bypassed entirely.

    Verifies that resolve_date_range skips the days-sentinel path when
    start_date is not None — including when days=0, which would otherwise
    set start_date to date(1900, 1, 1).
    """
    from datetime import date

    captured: dict = {}

    def _spy(ticker, exchange, start_date, end_date, **_):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        return _multi_day_df().copy()

    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "offline_mode", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.routes.timeseries_meta as ts_meta

    monkeypatch.setattr(ts_meta, "load_meta_timeseries_range", _spy)
    monkeypatch.setattr(ts_meta.pd, "to_datetime", lambda x: x)

    from backend.app import create_app

    client = TestClient(create_app())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json"
        "&start_date=2024-01-02&days=0"
    )
    assert resp.status_code == 200
    # days=0 must NOT override the explicit start_date with the 1900 sentinel
    assert captured["start_date"] == date(2024, 1, 2)


# ---- /timeseries/meta call-argument and branch-coverage tests -------------


def _client_with_spy(monkeypatch, loader_fn):
    """Return TestClient with a custom ``load_meta_timeseries_range`` loader."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "offline_mode", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.routes.timeseries_meta as ts_meta

    monkeypatch.setattr(ts_meta, "load_meta_timeseries_range", loader_fn)
    monkeypatch.setattr(ts_meta.pd, "to_datetime", lambda x: x)

    from backend.app import create_app

    app = create_app()
    return TestClient(app)


def test_load_called_with_resolved_dates(monkeypatch):
    """Route passes the resolved start_date/end_date to load_meta_timeseries_range."""
    from datetime import date

    captured: dict = {}

    def _spy(ticker, exchange, start_date, end_date, **_):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        return _multi_day_df().copy()

    client = _client_with_spy(monkeypatch, _spy)
    client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json"
        "&start_date=2024-01-01&end_date=2024-01-03"
    )
    assert captured["start_date"] == date(2024, 1, 1)
    assert captured["end_date"] == date(2024, 1, 3)


def test_end_date_with_days_derives_start(monkeypatch):
    """end_date supplied without start_date: start is end_date minus days."""
    from datetime import date, timedelta

    captured: dict = {}

    def _spy(ticker, exchange, start_date, end_date, **_):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        return _multi_day_df().copy()

    client = _client_with_spy(monkeypatch, _spy)
    client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json"
        "&end_date=2024-01-03&days=2"
    )
    assert captured["end_date"] == date(2024, 1, 3)
    assert captured["start_date"] == date(2024, 1, 3) - timedelta(days=2)


def test_days_zero_with_end_date_means_all_history(monkeypatch):
    """days=0 with explicit end_date selects all history up to end_date."""
    from datetime import date

    captured: dict = {}

    def _spy(ticker, exchange, start_date, end_date, **_):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        return _multi_day_df().copy()

    client = _client_with_spy(monkeypatch, _spy)
    client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json"
        "&end_date=2024-01-03&days=0"
    )
    assert captured["end_date"] == date(2024, 1, 3)
    assert captured["start_date"] == date(1900, 1, 1)  # "all history" sentinel


# ---- XSS regression tests (issue #3145) ------------------------------------
#
# html.escape() in render_timeseries_html (backend/utils/html_render.py) is
# the output-layer defence for reflected XSS.  The tests below are designed to
# be RED if html.escape() is removed from that function.
#
# Note on `scaling`: FastAPI constrains it to a float in [0.00001, 1_000_000],
# so it cannot carry HTML injection characters.  Safe rendering is exercised by
# test_timeseries_meta_formats_with_scaling[html] above.


@pytest.mark.parametrize("ticker,exchange", [
    ("<script>alert(1)</script>", "L"),
    ("ABC", '"><img src=x onerror=alert(1)>'),
])
def test_timeseries_meta_html_xss_rejected_by_validation(ticker, exchange, monkeypatch):
    """XSS payloads in ticker/exchange are rejected before they reach the HTML renderer.

    _TICKER_SEGMENT_RE rejects non-alphanumeric input with 400.  The response
    body (a JSON error) must not contain the raw tag regardless of format.
    """
    df = _sample_df()
    client = _client_with_df(monkeypatch, df)
    resp = client.get(
        "/timeseries/meta",
        params={"ticker": ticker, "exchange": exchange, "format": "html"},
    )
    assert resp.status_code == 400
    assert "<script>" not in resp.text.lower()
    assert "<img" not in resp.text.lower()


@pytest.mark.parametrize("xss_ticker,escaped_fragment", [
    ("<script>alert(1)</script>", "&lt;script&gt;"),
    ('"><img src=x onerror=alert(1)>', "&lt;img"),
])
def test_timeseries_html_xss_not_reflected(xss_ticker, escaped_fragment, monkeypatch):
    """/timeseries/html has no input validation; html.escape() must prevent injection.

    The ticker reaches render_timeseries_html verbatim, so this test confirms
    the output-layer escaping is sufficient on its own.  Exception() exercises
    the fallback path where ticker appears in both the page title and the
    DataFrame Ticker column — both surfaces must be safe.
    """
    client = _html_client(monkeypatch, Exception("no data"))
    resp = client.get(
        "/timeseries/html",
        params={"ticker": xss_ticker, "period": "1y", "interval": "1d"},
    )
    assert resp.status_code == 200
    assert "<script>" not in resp.text.lower()
    assert "<img" not in resp.text.lower()
    assert escaped_fragment in resp.text.lower()


def test_timeseries_meta_html_xss_exchange_from_resolver_is_escaped(monkeypatch):
    """Exchange returned by the internal resolver is HTML-escaped in the HTML response.

    _TICKER_SEGMENT_RE only validates user-supplied input; tickers returned by
    _resolve_full_ticker bypass the regex.  This test exercises that defence-in-
    depth path: even if an internally-resolved exchange carries HTML-special chars,
    render_timeseries_html must neutralise them via html.escape().
    """
    import backend.routes.timeseries_meta as ts_meta

    df = _sample_df()
    client = _client_with_df(monkeypatch, df)
    # Override the internal resolver to return an exchange with a raw script tag.
    # No exchange param in the request → validation is bypassed for this path.
    monkeypatch.setattr(
        ts_meta.instrument_api,
        "_resolve_full_ticker",
        lambda t, latest: ("ABC", "<SCRIPT>EVIL</SCRIPT>"),
    )
    resp = client.get("/timeseries/meta", params={"ticker": "ABC", "format": "html"})
    assert resp.status_code == 200
    assert "<script>" not in resp.text.lower()
    assert "&lt;script&gt;" in resp.text.lower()


def test_timeseries_html_xss_ticker_column_in_dataframe_is_escaped(monkeypatch):
    """XSS in the DataFrame Ticker column is escaped when rendering the HTML table.

    Distinct from test_timeseries_html_xss_not_reflected (fallback path): here
    fetch_yahoo_timeseries succeeds and returns a DataFrame whose Ticker column
    already contains an XSS payload.  Confirms df.to_html() uses escape=True.
    The page title is safe ('ABC Price History'); the only injection surface is
    the table cell — deliberately isolated to test that specific layer.
    """
    xss = "<script>alert(1)</script>"
    df = pd.DataFrame([{
        "Date": "2024-01-01",
        "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5,
        "Volume": 100, "Ticker": xss, "Source": "Yahoo",
    }])
    client = _html_client(monkeypatch, df)
    # ticker param is benign; injection surface is the DataFrame Ticker column only
    resp = client.get(
        "/timeseries/html",
        params={"ticker": "ABC", "period": "1y", "interval": "1d"},
    )
    assert resp.status_code == 200
    assert "<script>" not in resp.text.lower()
    assert "&lt;script&gt;" in resp.text.lower()


def test_timeseries_meta_json_output_not_html_escaped(monkeypatch):
    """JSON output must not apply html.escape() — raw values are safe in JSON.

    Verifies that the fix does not accidentally escape ticker values in JSON
    responses (acceptance criterion: JSON and CSV output paths are unaffected).
    """
    df = _sample_df()
    client = _client_with_df(monkeypatch, df)
    resp = client.get(
        "/timeseries/meta",
        params={"ticker": "ABC", "exchange": "L", "format": "json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "ABC.L"  # raw ticker — no &amp; or &lt; entities


def test_timeseries_meta_csv_output_not_html_escaped(monkeypatch):
    """CSV output must not apply html.escape() — raw values are safe in CSV.

    Verifies that the fix does not accidentally introduce HTML entities into
    CSV responses (acceptance criterion: JSON and CSV output paths are unaffected).
    """
    df = _sample_df()
    client = _client_with_df(monkeypatch, df)
    resp = client.get(
        "/timeseries/meta",
        params={"ticker": "ABC", "exchange": "L", "format": "csv"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "&lt;" not in resp.text   # no HTML-escaped angle brackets
    assert "&amp;" not in resp.text  # no HTML-escaped ampersands
