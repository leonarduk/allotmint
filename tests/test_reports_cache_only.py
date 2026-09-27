"""Report aggregate sections read cached prices and FX only (#8053).

Report requests are built synchronously, so the sector/region/concentration
sections get the same cache-only treatment as the portfolio page routes
(#8028); date-range sections stay live.
"""

import pandas as pd
import pytest

import backend.utils.fx_rates as fx_rates
from backend import reports
from backend.common import portfolio_utils
from backend.routes import portfolio as portfolio_routes
from backend.timeseries import cache, refresh_queue

PORTFOLIO = {"accounts": [{"owner": "alice", "holdings": [{"ticker": "AAPL.N", "exchange": "N", "units": 2}]}]}

AGGREGATE_SECTIONS = [
    (reports._build_portfolio_sectors_section, reports.PORTFOLIO_SECTORS_SECTION),
    (reports._build_portfolio_regions_section, reports.PORTFOLIO_REGIONS_SECTION),
    (reports._build_portfolio_concentration_section, reports.PORTFOLIO_CONCENTRATION_SECTION),
    (reports._build_portfolio_sectors_section, reports.AUDIT_REPORT_TEMPLATE.sections[1]),
    (reports._build_portfolio_regions_section, reports.AUDIT_REPORT_TEMPLATE.sections[2]),
    (reports._build_portfolio_concentration_section, reports.AUDIT_REPORT_TEMPLATE.sections[3]),
]


def _explode(name):
    def fetch(*_args, **_kwargs):
        raise AssertionError(f"report aggregate sections must not call {name}")

    return fetch


@pytest.fixture
def usd_holding_without_changes(monkeypatch, tmp_path):
    """Alice holds 2 AAPL.N; the snapshot has a USD price but no 7d/30d changes.

    Aggregating it reaches both live paths: ``_fx_to_base`` for the USD price
    and ``price_change_pct`` for the missing changes. Every live source raises.
    """
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache.config, "offline_mode", False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.setattr(cache, "_FX_FRAMES", {})
    cache._load_meta_timeseries_cached.cache_clear()
    cache._memoized_range_cached.cache_clear()

    fx = pd.DataFrame({"Date": pd.bdate_range(end=cache._last_close_target(), periods=30), "Rate": 0.75})
    path = cache._fx_cache_path("USD")
    cache._ensure_local_dir(path)
    fx.to_parquet(path, index=False)

    monkeypatch.setattr(cache, "fetch_meta_timeseries", _explode("fetch_meta_timeseries"))
    monkeypatch.setattr(cache, "fetch_fx_rate_range_live", _explode("cache.fetch_fx_rate_range_live"))
    monkeypatch.setattr(fx_rates, "fetch_fx_rate_range_live", _explode("fx_rates.fetch_fx_rate_range_live"))
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", _explode("fetch_fx_rate_range"))
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {"AAPL.N": {"last_price": 100.0, "price_currency": "USD"}})
    monkeypatch.setattr(reports.portfolio_mod, "build_owner_portfolio", lambda *_a, **_k: PORTFOLIO)
    monkeypatch.setattr(portfolio_routes, "_build_group_portfolio", lambda *_: PORTFOLIO)


def _market_values(rows):
    # Audit-template rows label the value ``value``; the others ``market_value_gbp``.
    return [row.get("market_value_gbp", row.get("value")) for row in rows]


@pytest.mark.parametrize(("builder", "section"), AGGREGATE_SECTIONS)
def test_aggregate_sections_price_from_cached_fx_with_no_live_calls(usd_holding_without_changes, builder, section):
    context = reports.ReportContext(owner="alice", start=None, end=None)

    rows = builder(context, section)

    assert rows
    assert pytest.approx(150.0) in _market_values(rows)
    assert cache.is_cache_only() is False


def test_report_concentration_matches_the_instruments_page(usd_holding_without_changes):
    context = reports.ReportContext(owner="alice", start=None, end=None)

    report_rows = reports._build_portfolio_concentration_section(context, reports.PORTFOLIO_CONCENTRATION_SECTION)
    page_rows = portfolio_routes.group_instruments("all", owner=None, account_type=None, as_of=None)

    holding = next(row for row in report_rows if row.get("row_type") == "holding")
    assert holding["market_value_gbp"] == pytest.approx(page_rows[0]["market_value_gbp"])
    # Missing cached prices are queued for the background refresh, not fetched.
    assert ("AAPL", "N") in refresh_queue.pending()


@pytest.mark.parametrize("source", ["portfolio.sectors", "portfolio.regions", "portfolio.concentration"])
def test_registered_aggregate_builders_run_cache_only(monkeypatch, source):
    seen = []
    monkeypatch.setattr(reports.portfolio_mod, "build_owner_portfolio", lambda *_a, **_k: PORTFOLIO)
    for name in ("aggregate_by_sector", "aggregate_by_region", "aggregate_by_ticker"):
        monkeypatch.setattr(portfolio_utils, name, lambda *_a, **_k: seen.append(cache.is_cache_only()) or [])
    schema = next(s for s in reports.AUDIT_REPORT_TEMPLATE.sections if s.source == source)

    reports.SECTION_BUILDERS[source](reports.ReportContext(owner="alice", start=None, end=None), schema)

    assert seen == [True]


class _Observed(Exception):
    pass


@pytest.mark.parametrize(
    ("source", "target", "name"),
    [
        ("allocation", reports, "_compile_summary"),  # allocation() resolves its date via performance()
        ("performance.history", reports, "_compile_summary"),
        ("performance.metrics", reports, "_compile_summary"),
    ],
)
def test_date_range_sections_stay_live(monkeypatch, source, target, name):
    """Only the point-in-time aggregate sections are cache-only; history can still backfill."""
    seen = []

    def observe(*_args, **_kwargs):
        seen.append(cache.is_cache_only())
        raise _Observed

    monkeypatch.setattr(target, name, observe)
    schema = reports.ReportSectionSchema(id="s", title="s", source=source, columns=())

    try:
        reports.SECTION_BUILDERS[source](reports.ReportContext(owner="alice", start=None, end=None), schema)
    except _Observed:
        pass

    assert seen == [False]
