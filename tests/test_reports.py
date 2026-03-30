import io
import json
import sys
import types
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import backend.reports as reports


def test_load_transactions_handles_malformed_json(tmp_path, monkeypatch, caplog):
    owner = "alice"
    owner_dir = tmp_path / owner
    owner_dir.mkdir()

    good = owner_dir / "good_transactions.json"
    good.write_text(json.dumps({"transactions": [{"id": 1}]}))

    bad = owner_dir / "bad_transactions.json"
    bad.write_text("{not json")

    monkeypatch.setattr(reports, "_transaction_roots", lambda: [str(tmp_path)])
    monkeypatch.setattr(reports.config, "app_env", "local")

    with caplog.at_level("WARNING"):
        records = reports._load_transactions(owner)

    assert records == [{"id": 1}]
    assert "failed to read" in caplog.text


def test_load_transactions_s3(monkeypatch, caplog):
    owner = "alice"
    monkeypatch.setattr(reports.config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "bucket")

    class FakeBotoCoreError(Exception):
        pass

    class FakeClientError(Exception):
        pass

    exceptions_mod = types.ModuleType("exceptions")
    exceptions_mod.BotoCoreError = FakeBotoCoreError
    exceptions_mod.ClientError = FakeClientError
    botocore_mod = types.ModuleType("botocore")
    botocore_mod.exceptions = exceptions_mod
    monkeypatch.setitem(sys.modules, "botocore", botocore_mod)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", exceptions_mod)

    class FakePaginator:
        def paginate(self, Bucket, Prefix):
            return [
                {
                    "Contents": [
                        {"Key": f"transactions/{owner}/good_transactions.json"},
                        {"Key": f"transactions/{owner}/error_transactions.json"},
                        {"Key": f"transactions/{owner}/ignore.txt"},
                    ]
                }
            ]

    class FakeS3Client:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator()

        def get_object(self, Bucket, Key):
            if Key.endswith("error_transactions.json"):
                raise FakeBotoCoreError("boom")
            data = b'{"transactions": [{"id": 1}]}'
            return {"Body": io.BytesIO(data)}

    boto3_mod = types.ModuleType("boto3")
    boto3_mod.client = lambda name: FakeS3Client()
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)

    with caplog.at_level("WARNING"):
        records = reports._load_transactions(owner)

    assert records == [{"id": 1}]
    assert "failed to load" in caplog.text


def test_compile_report_filters_and_totals(monkeypatch):
    txs = [
        {"date": "2024-01-01", "type": "SELL", "amount_minor": 1000},
        {"date": "2024-01-02", "type": "SELL", "amount_minor": 2000},
        {"date": "2024-01-03", "type": "DIVIDEND", "amount_minor": 500},
        {"date": "2024-01-04", "type": "INTEREST", "amount_minor": 300},
    ]

    monkeypatch.setattr(reports, "_load_transactions", lambda owner: txs)
    performance = {
        "history": [
            {"date": "2024-01-01", "cumulative_return": 0.1},
            {"date": "2024-01-02", "cumulative_return": 0.2},
            {"date": "2024-01-03", "cumulative_return": 0.3},
            {"date": "2024-01-04", "cumulative_return": 0.4},
        ],
        "max_drawdown": -0.1,
    }
    monkeypatch.setattr(
        "backend.common.portfolio_utils.compute_owner_performance",
        lambda owner, **kwargs: performance,
    )

    start = date(2024, 1, 2)
    end = date(2024, 1, 3)
    data = reports.compile_report("alice", start=start, end=end)

    assert data.realized_gains_gbp == 20.0
    assert data.income_gbp == 5.0
    assert data.cumulative_return == 0.3
    assert data.max_drawdown == -0.1


def test_load_transactions_requires_data_bucket(monkeypatch):
    monkeypatch.setattr(reports.config, "app_env", "aws")
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    with pytest.raises(RuntimeError, match="DATA_BUCKET environment variable is required in AWS"):
        reports._load_transactions("alice")


def test_load_transactions_skips_missing_owner_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(reports.config, "app_env", "local", raising=False)
    monkeypatch.setattr(reports, "_transaction_roots", lambda: [tmp_path.as_posix()])

    assert reports._load_transactions("alice") == []


def test_build_report_document_uses_context(monkeypatch):
    history = [
        {
            "date": "2024-01-01",
            "value": 100.0,
            "daily_return": 0.1,
            "weekly_return": 0.2,
            "cumulative_return": 0.3,
            "drawdown": 0.0,
        },
    ]
    summary = reports.ReportData(
        owner="alice",
        start=None,
        end=None,
        realized_gains_gbp=15.0,
        income_gbp=5.0,
        cumulative_return=0.3,
        max_drawdown=-0.1,
        history=history,
    )
    performance = {"history": history, "reporting_date": "2024-01-01", "max_drawdown": -0.1}

    monkeypatch.setattr(
        reports, "_compile_summary", lambda owner, start, end: (summary, performance)
    )
    monkeypatch.setattr(
        reports,
        "_load_transactions",
        lambda owner: [
            {"date": "2024-01-01", "type": "SELL", "amount_minor": 1000, "currency": "GBP"}
        ],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "portfolio_value_breakdown",
        lambda owner, date: [
            {"ticker": "ABC", "exchange": "L", "units": 2, "price": 10.5, "value": 21.0}
        ],
    )

    document = reports.build_report_document("performance-summary", "alice")
    assert document.template.template_id == "performance-summary"
    metrics = {row["metric"]: row["value"] for row in document.sections[0].rows}
    assert metrics["Realized gains"] == 15.0
    assert metrics["Transactions"] == 1
    history_rows = document.sections[1].rows
    assert history_rows[0]["date"] == "2024-01-01"


# ---------------------------------------------------------------------------
# Helpers shared across portfolio section tests
# ---------------------------------------------------------------------------

def _portfolio_template():
    return reports.ReportTemplate(
        template_id="portfolio-insights",
        name="Portfolio insights",
        description="",
        sections=(
            reports.PORTFOLIO_OVERVIEW_SECTION,
            reports.PORTFOLIO_SECTORS_SECTION,
            reports.PORTFOLIO_REGIONS_SECTION,
            reports.PORTFOLIO_CONCENTRATION_SECTION,
            reports.PORTFOLIO_VAR_SECTION,
        ),
    )


def _preloaded_context(portfolio: dict) -> reports.ReportContext:
    """Return a ReportContext with owner_portfolio() pre-loaded to avoid I/O."""
    ctx = reports.ReportContext(owner="alice", start=None, end=None)
    ctx._owner_portfolio = portfolio
    ctx._owner_portfolio_loaded = True
    return ctx


# ---------------------------------------------------------------------------
# Happy-path integration test
# ---------------------------------------------------------------------------

def test_portfolio_section_builders(monkeypatch):
    portfolio_payload = {
        "total_value_estimate_gbp": 1000.0,
        "accounts": [
            {
                "account_type": "ISA",
                "value_estimate_gbp": 700.0,
                "holdings": [
                    {"asset_class": "Equity", "market_value_gbp": 400.0},
                    {"asset_class": "Bond", "market_value_gbp": 300.0},
                ],
            },
            {
                "account_type": "GIA",
                "value_estimate_gbp": 300.0,
                "holdings": [{"asset_class": "Equity", "market_value_gbp": 300.0}],
            },
        ],
    }
    build_calls = {"count": 0}
    build_pricing_dates: list[date | None] = []

    def _build_owner_portfolio(owner, pricing_date=None):
        build_calls["count"] += 1
        build_pricing_dates.append(pricing_date)
        return portfolio_payload

    monkeypatch.setattr(reports.portfolio_mod, "build_owner_portfolio", _build_owner_portfolio)
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_sector",
        lambda portfolio: [
            {
                "sector": "Tech",
                "market_value_gbp": 700.0,
                "gain_gbp": 100.0,
                "cost_gbp": 600.0,
                "gain_pct": 16.666666,
                "contribution_pct": 8.0,
            },
            {
                "sector": "Utilities",
                "market_value_gbp": 300.0,
                "gain_gbp": 20.0,
                "cost_gbp": 280.0,
                "gain_pct": 7.142857,
                "contribution_pct": 2.0,
            },
        ],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_region",
        lambda portfolio: [
            {
                "region": "UK",
                "market_value_gbp": 600.0,
                "gain_gbp": 80.0,
                "cost_gbp": 520.0,
                "gain_pct": 15.384615,
                "contribution_pct": 6.0,
            },
            {
                "region": "US",
                "market_value_gbp": 400.0,
                "gain_gbp": 40.0,
                "cost_gbp": 360.0,
                "gain_pct": 11.111111,
                "contribution_pct": 4.0,
            },
        ],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_ticker",
        lambda portfolio: [
            {"ticker": "AAA.L", "market_value_gbp": 600.0},
            {"ticker": "BBB.L", "market_value_gbp": 400.0},
        ],
    )
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence, include_cash=True: {"confidence": confidence, "1d": 12.345, "10d": 34.567},
    )
    monkeypatch.setattr(reports.risk, "compute_sharpe_ratio", lambda owner: 1.23456)
    monkeypatch.setattr(reports, "get_template", lambda template_id, store=None: _portfolio_template())

    document = reports.build_report_document(
        "portfolio-insights", "alice", end=date(2024, 1, 31)
    )
    sources = {section.schema.source: section.rows for section in document.sections}

    overview_rows = sources["portfolio.overview"]
    assert any(row["label"] == "Total portfolio value" and row["value"] == 1000.0 for row in overview_rows)
    assert any(
        row["category"] == "asset_class" and row["label"] == "Equity" and row["value"] == 700.0
        for row in overview_rows
    )

    sectors_rows = sources["portfolio.sectors"]
    assert sectors_rows[0]["sector"] == "Tech"
    assert sectors_rows[0]["weight_pct"] == 70.0

    regions_rows = sources["portfolio.regions"]
    assert regions_rows[0]["region"] == "UK"
    assert regions_rows[0]["weight_pct"] == 60.0

    concentration_rows = sources["portfolio.concentration"]
    holding_rows = [r for r in concentration_rows if r["row_type"] == "holding"]
    summary_rows = [r for r in concentration_rows if r["row_type"] == "summary"]
    assert len(summary_rows) == 1
    assert holding_rows[0]["ticker"] == "AAA.L"
    assert holding_rows[0]["hhi"] is None
    summary = summary_rows[0]
    assert summary["hhi"] == pytest.approx(0.52, abs=1e-6)
    assert summary["top_n_weight_pct"] == pytest.approx(100.0, abs=1e-4)
    # n_holdings is total portfolio holding count, not the top-N cap
    assert summary["n_holdings"] == 2

    var_rows = sources["portfolio.var"]
    assert [row["metric"] for row in var_rows] == ["VaR (95%)", "VaR (99%)", "Sharpe ratio"]
    assert any(row["metric"] == "Sharpe ratio" and row["value"] == pytest.approx(1.23456, abs=1e-6) for row in var_rows)
    # portfolio is loaded exactly once for all five sections
    assert build_calls["count"] == 1
    assert build_pricing_dates == [date(2024, 1, 31)]


# ---------------------------------------------------------------------------
# Overview builder edge cases
# ---------------------------------------------------------------------------

def test_overview_empty_accounts(monkeypatch):
    """Overview with no accounts produces only summary rows (no account/asset_class rows)."""
    ctx = _preloaded_context({"total_value_estimate_gbp": 500.0, "accounts": []})
    result = reports._build_portfolio_overview_section(ctx, reports.PORTFOLIO_OVERVIEW_SECTION)
    categories = [r["category"] for r in result]
    assert "summary" in categories
    assert "account" not in categories
    assert "asset_class" not in categories
    summary_rows = [r for r in result if r["label"] == "Total portfolio value"]
    assert summary_rows[0]["value"] == 500.0


def test_overview_non_dict_account_entries_are_skipped(monkeypatch):
    """Non-dict entries in the accounts list must be skipped in both passes without raising."""
    ctx = _preloaded_context({
        "total_value_estimate_gbp": 200.0,
        "accounts": [
            "not-a-dict",
            None,
            {"account_type": "ISA", "value_estimate_gbp": 200.0, "holdings": [
                {"asset_class": "Equity", "market_value_gbp": 200.0}
            ]},
        ],
    })
    result = reports._build_portfolio_overview_section(ctx, reports.PORTFOLIO_OVERVIEW_SECTION)
    account_rows = [r for r in result if r["category"] == "account"]
    # Only the dict account should produce a row
    assert len(account_rows) == 1
    assert account_rows[0]["label"] == "ISA"
    # Asset class total from the one valid dict account
    asset_rows = [r for r in result if r["category"] == "asset_class"]
    assert len(asset_rows) == 1
    assert asset_rows[0]["label"] == "Equity"


# ---------------------------------------------------------------------------
# Sectors / regions edge cases
# ---------------------------------------------------------------------------

def test_sectors_weight_pct_sums_to_100(monkeypatch):
    """weight_pct values across all sector rows should sum to 100%."""
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_sector",
        lambda portfolio: [
            {"sector": "Tech", "market_value_gbp": 600.0},
            {"sector": "Finance", "market_value_gbp": 250.0},
            {"sector": "Energy", "market_value_gbp": 150.0},
        ],
    )
    ctx = _preloaded_context({"accounts": []})
    result = reports._build_portfolio_sectors_section(ctx, reports.PORTFOLIO_SECTORS_SECTION)
    total_weight = sum(r["weight_pct"] for r in result)
    assert total_weight == pytest.approx(100.0, abs=1e-6)


def test_regions_weight_pct_sums_to_100(monkeypatch):
    """weight_pct values across all region rows should sum to 100%."""
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_region",
        lambda portfolio: [
            {"region": "UK", "market_value_gbp": 700.0},
            {"region": "US", "market_value_gbp": 300.0},
        ],
    )
    ctx = _preloaded_context({"accounts": []})
    result = reports._build_portfolio_regions_section(ctx, reports.PORTFOLIO_REGIONS_SECTION)
    total_weight = sum(r["weight_pct"] for r in result)
    assert total_weight == pytest.approx(100.0, abs=1e-6)


def test_sectors_zero_total_value_yields_none_weight(monkeypatch):
    """When all market values are 0, weight_pct should be None (no division)."""
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_sector",
        lambda portfolio: [
            {"sector": "Tech", "market_value_gbp": 0.0},
        ],
    )
    ctx = _preloaded_context({"accounts": []})
    result = reports._build_portfolio_sectors_section(ctx, reports.PORTFOLIO_SECTORS_SECTION)
    assert result[0]["weight_pct"] is None


# ---------------------------------------------------------------------------
# Concentration edge cases
# ---------------------------------------------------------------------------

def test_concentration_n_holdings_is_total_not_top_n(monkeypatch):
    """n_holdings in the summary row must reflect total portfolio holding count,
    not the capped top-10 slice."""
    # 12 holdings: top-10 slice != total
    tickers = [
        {"ticker": f"T{i:02d}.L", "market_value_gbp": float(100 - i * 5)}
        for i in range(12)
    ]
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_ticker",
        lambda portfolio: tickers,
    )
    ctx = _preloaded_context({"accounts": []})
    result = reports._build_portfolio_concentration_section(ctx, reports.PORTFOLIO_CONCENTRATION_SECTION)

    holding_rows = [r for r in result if r["row_type"] == "holding"]
    summary_rows = [r for r in result if r["row_type"] == "summary"]
    assert len(holding_rows) == 10
    assert len(summary_rows) == 1
    summary = summary_rows[0]
    # Total holdings is 12, not 10
    assert summary["n_holdings"] == 12
    # HHI is computed over all 12 holdings
    total_value = sum(float(t["market_value_gbp"]) for t in tickers)
    expected_hhi = sum((t["market_value_gbp"] / total_value) ** 2 for t in tickers)
    assert summary["hhi"] == pytest.approx(expected_hhi, abs=1e-6)
    # top_n_weight_pct covers only the top-10 by value
    top10_weight = sum(sorted(
        [t["market_value_gbp"] for t in tickers], reverse=True
    )[:10]) / total_value * 100.0
    assert summary["top_n_weight_pct"] == pytest.approx(top10_weight, abs=1e-4)


# ---------------------------------------------------------------------------
# VaR edge cases
# ---------------------------------------------------------------------------

def test_portfolio_var_partial_failure_one_confidence_level(monkeypatch):
    """If 0.95 raises but 0.99 succeeds, the section returns only the 0.99 rows."""
    monkeypatch.setattr(reports.portfolio_mod, "build_owner_portfolio",
                        lambda owner, pricing_date=None: {"accounts": []})

    call_count = {"n": 0}

    def _var(owner, confidence):
        call_count["n"] += 1
        if confidence == 0.95:
            raise ValueError("no data for 0.95")
        return {"confidence": confidence, "1d": 5.0, "10d": 15.0}

    monkeypatch.setattr(
        reports,
        "risk",
        SimpleNamespace(
            compute_portfolio_var=_var,
            compute_sharpe_ratio=lambda owner: None,
        ),
    )
    ctx = reports.ReportContext(owner="alice", start=None, end=None)
    result = reports._build_portfolio_var_section(ctx, reports.PORTFOLIO_VAR_SECTION)
    # Only the 0.99 row is retained; Sharpe is omitted because None.
    assert result == [{"metric": "VaR (99%)", "value": 5.0, "units": "GBP"}]
    assert call_count["n"] == 2  # both confidence levels were attempted


def test_portfolio_var_omits_sharpe_row_when_sharpe_fails(monkeypatch):
    """When VaR succeeds but compute_sharpe_ratio raises, no Sharpe row is appended."""
    monkeypatch.setattr(reports.portfolio_mod, "build_owner_portfolio",
                        lambda owner, pricing_date=None: {"accounts": []})
    monkeypatch.setattr(
        reports,
        "risk",
        SimpleNamespace(
            compute_portfolio_var=lambda owner, confidence, include_cash=True: {"confidence": confidence, "1d": 10.0, "10d": 20.0},
            compute_sharpe_ratio=Mock(side_effect=ValueError("no returns")),
        ),
    )
    ctx = reports.ReportContext(owner="alice", start=None, end=None)
    result = reports._build_portfolio_var_section(ctx, reports.PORTFOLIO_VAR_SECTION)
    assert [row["metric"] for row in result] == ["VaR (95%)", "VaR (99%)"]
    assert not any(r["metric"] == "Sharpe ratio" for r in result)


def test_portfolio_var_returns_empty_when_var_rows_unavailable(monkeypatch):
    """VaR builder returns [] when both confidence-level calls raise."""
    monkeypatch.setattr(reports.portfolio_mod, "build_owner_portfolio",
                        lambda owner, pricing_date=None: {"accounts": []})
    monkeypatch.setattr(
        reports,
        "risk",
        SimpleNamespace(
            compute_portfolio_var=Mock(side_effect=ValueError("no var rows")),
            compute_sharpe_ratio=Mock(return_value=2.0),
        ),
    )
    ctx = reports.ReportContext(owner="alice", start=None, end=None)
    result = reports._build_portfolio_var_section(ctx, reports.PORTFOLIO_VAR_SECTION)
    assert result == []


# ---------------------------------------------------------------------------
# Caching / module-missing paths
# ---------------------------------------------------------------------------

def test_owner_portfolio_failure_is_cached_once_per_report_build(monkeypatch):
    call_count = {"count": 0}
    var_call_count = {"count": 0}

    def _raise_on_build(owner, pricing_date=None):
        call_count["count"] += 1
        raise ValueError("missing portfolio")

    monkeypatch.setattr(reports.portfolio_mod, "build_owner_portfolio", _raise_on_build)
    monkeypatch.setattr(
        reports.portfolio_utils, "aggregate_by_sector", lambda portfolio: pytest.fail("unexpected call")
    )
    monkeypatch.setattr(
        reports.portfolio_utils, "aggregate_by_region", lambda portfolio: pytest.fail("unexpected call")
    )
    monkeypatch.setattr(
        reports.portfolio_utils, "aggregate_by_ticker", lambda portfolio: pytest.fail("unexpected call")
    )
    monkeypatch.setattr(
        reports,
        "risk",
        SimpleNamespace(
            compute_portfolio_var=lambda owner, confidence=0.95: var_call_count.__setitem__(
                "count", var_call_count["count"] + 1
            ),
            compute_sharpe_ratio=lambda owner: pytest.fail("unexpected sharpe call"),
        ),
    )
    monkeypatch.setattr(reports, "get_template", lambda template_id, store=None: _portfolio_template())

    document = reports.build_report_document(
        "portfolio-insights",
        "alice",
        end=date(2024, 1, 31),
    )

    assert call_count["count"] == 1
    sources = {section.schema.source: section.rows for section in document.sections}
    assert sources["portfolio.overview"] == ()
    assert sources["portfolio.sectors"] == ()
    assert sources["portfolio.regions"] == ()
    assert sources["portfolio.concentration"] == ()
    assert sources["portfolio.var"] == ()
    assert var_call_count["count"] == 0


def test_portfolio_sections_return_empty_when_optional_modules_missing(monkeypatch):
    monkeypatch.setattr(reports, "portfolio_mod", None)
    monkeypatch.setattr(reports, "risk", None)

    context = reports.ReportContext(owner="alice", start=None, end=None)

    assert reports._build_portfolio_overview_section(context, reports.PORTFOLIO_OVERVIEW_SECTION) == []
    assert reports._build_portfolio_sectors_section(context, reports.PORTFOLIO_SECTORS_SECTION) == []
    assert reports._build_portfolio_regions_section(context, reports.PORTFOLIO_REGIONS_SECTION) == []
    assert reports._build_portfolio_concentration_section(context, reports.PORTFOLIO_CONCENTRATION_SECTION) == []
    assert reports._build_portfolio_var_section(context, reports.PORTFOLIO_VAR_SECTION) == []


# ---------------------------------------------------------------------------
# Template store / existing tests
# ---------------------------------------------------------------------------

def test_list_template_metadata_merges_user_templates(tmp_path):
    reports.get_template_store.cache_clear()
    store = reports.FileTemplateStore(tmp_path)
    definition = {
        "template_id": "custom",
        "name": "Custom",
        "description": "",
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "source": "performance.metrics",
                "columns": [
                    {"key": "metric", "label": "Metric", "type": "string"},
                ],
            }
        ],
    }
    store.create_template(definition)

    templates = reports.list_template_metadata(store=store)
    ids = {t["template_id"] for t in templates}
    assert "performance-summary" in ids
    assert "custom" in ids


def test_create_update_delete_user_template(tmp_path):
    store = reports.FileTemplateStore(tmp_path)
    definition = {
        "template_id": "custom",
        "name": "Custom",
        "description": "",
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "source": "performance.metrics",
                "columns": [
                    {"key": "metric", "label": "Metric", "type": "string"},
                ],
            }
        ],
    }

    template = reports.create_user_template(definition, store=store)
    assert template.template_id == "custom"

    updated = reports.update_user_template(
        "custom",
        {
            "name": "Custom v2",
            "description": "",
            "sections": definition["sections"],
        },
        store=store,
    )
    assert updated.name == "Custom v2"

    reports.delete_user_template("custom", store=store)
    assert store.get_template("custom") is None


def test_get_template_returns_user_definition(tmp_path, monkeypatch):
    original_get_store = reports.get_template_store
    original_get_store.cache_clear()
    store = reports.FileTemplateStore(tmp_path)
    definition = {
        "template_id": "custom",
        "name": "Custom",
        "description": "",
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "source": "performance.metrics",
                "columns": [{"key": "metric", "label": "Metric", "type": "string"}],
            }
        ],
    }
    store.create_template(definition)
    monkeypatch.setattr(reports, "get_template_store", lambda: store)

    template = reports.get_template("custom")

    assert template is not None
    assert template.template_id == "custom"


def test_get_template_returns_builtin_audit_report():
    template = reports.get_template("audit-report")
    assert template is not None
    assert template.template_id == "audit-report"


def test_get_template_returns_none_for_missing(monkeypatch):
    original_get_store = reports.get_template_store
    original_get_store.cache_clear()
    monkeypatch.setattr(
        reports,
        "get_template_store",
        lambda: SimpleNamespace(get_template=lambda template_id: None),
    )

    assert reports.get_template("missing") is None

    original_get_store.cache_clear()


def test_file_template_store_filters_invalid_definitions(tmp_path, caplog):
    store = reports.FileTemplateStore(tmp_path)
    valid = {
        "template_id": "valid",
        "name": "Valid",
        "description": "",
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "source": "performance.metrics",
                "columns": [
                    {"key": "metric", "label": "Metric", "type": "string"},
                ],
            }
        ],
    }
    store.create_template(valid)

    # Corrupt JSON file should be skipped with a warning
    (tmp_path / "broken.json").write_text("{not json")

    # Invalid schema (missing name) should also be skipped
    (tmp_path / "invalid.json").write_text(
        json.dumps(
            {
                "template_id": "invalid",
                "sections": [],
            }
        )
    )

    with caplog.at_level("WARNING", logger=reports.logger.name):
        templates = store.list_templates()

    assert [t["template_id"] for t in templates] == ["valid"]
    assert "failed to load report template" in caplog.text
    assert "invalid template definition" in caplog.text


def test_file_template_store_get_template_handles_invalid_json(tmp_path, caplog):
    store = reports.FileTemplateStore(tmp_path)
    (tmp_path / "example.json").write_text("{not json")

    with caplog.at_level("WARNING", logger=reports.logger.name):
        template = store.get_template("example")

    assert template is None
    assert "failed to load report template" in caplog.text


def test_get_template_store_requires_aws_configuration(monkeypatch):
    reports.get_template_store.cache_clear()
    monkeypatch.setattr(reports.config, "app_env", "aws", raising=False)
    monkeypatch.delenv("REPORT_TEMPLATES_TABLE", raising=False)

    with pytest.raises(RuntimeError, match="REPORT_TEMPLATES_TABLE"):
        reports.get_template_store()


def test_get_template_store_local_returns_file_store(monkeypatch, tmp_path):
    reports.get_template_store.cache_clear()
    monkeypatch.setattr(reports.config, "app_env", "local", raising=False)
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)

    store = reports.get_template_store()

    assert isinstance(store, reports.FileTemplateStore)
    assert store.root == tmp_path / "reports"


def test_report_context_transactions_filters_and_sorts(monkeypatch):
    raw = [
        {"date": "2024-01-02", "type": "sell", "amount_minor": 200},
        {"date": "invalid", "type": "buy", "amount_minor": 100},
        {"date": "2024-01-01", "type": "buy", "amount_minor": 100},
    ]

    monkeypatch.setattr(reports, "_load_transactions", lambda owner: raw)
    monkeypatch.setattr(
        reports,
        "_compile_summary",
        lambda owner, start, end: (
            reports.ReportData(
                owner=owner,
                start=None,
                end=None,
                realized_gains_gbp=0.0,
                income_gbp=0.0,
                cumulative_return=None,
                max_drawdown=None,
            ),
            {},
        ),
    )

    context = reports.ReportContext("alice", start=date(2024, 1, 1), end=None)
    rows = context.transactions()

    assert [row["date"] for row in rows] == ["2024-01-01", "2024-01-02", "invalid"]


def test_report_context_allocation_handles_errors(monkeypatch):
    summary = reports.ReportData(
        owner="alice",
        start=None,
        end=None,
        realized_gains_gbp=0.0,
        income_gbp=0.0,
        cumulative_return=None,
        max_drawdown=None,
    )
    monkeypatch.setattr(reports, "_compile_summary", lambda owner, start, end: (summary, {}))
    monkeypatch.setattr(
        reports.portfolio_utils,
        "portfolio_value_breakdown",
        lambda owner, date: (_ for _ in ()).throw(FileNotFoundError()),
    )

    context = reports.ReportContext("alice", start=None, end=None)
    assert context.allocation() == []


def test_report_context_allocation_rounds_and_sorts(monkeypatch):
    summary = reports.ReportData(
        owner="alice",
        start=None,
        end=date(2024, 1, 1),
        realized_gains_gbp=0.0,
        income_gbp=0.0,
        cumulative_return=None,
        max_drawdown=None,
    )
    perf = {"reporting_date": "2024-01-01"}

    monkeypatch.setattr(reports, "_compile_summary", lambda owner, start, end: (summary, perf))

    rows = [
        {"ticker": "XYZ.L", "exchange": "L", "units": 1.23456, "price": 9.8765, "value": 123.4567},
        {"ticker": "ABC.N", "exchange": "N", "units": None, "price": None, "value": None},
    ]

    def fake_breakdown(owner, date):
        assert date == "2024-01-01"
        return rows

    monkeypatch.setattr(reports.portfolio_utils, "portfolio_value_breakdown", fake_breakdown)

    context = reports.ReportContext("alice", start=None, end=date(2024, 1, 1))
    allocation = context.allocation()

    assert allocation[0] == {
        "ticker": "XYZ.L",
        "exchange": "L",
        "units": 1.2346,
        "price": 9.8765,
        "value": 123.46,
    }
    assert allocation[1]["ticker"] == "ABC.N"


def test_build_report_document_warns_on_missing_builder(monkeypatch, caplog):
    template = reports.ReportTemplate(
        template_id="custom",
        name="Custom",
        description="",
        sections=(
            reports.ReportSectionSchema(
                id="mystery",
                title="Mystery",
                source="unknown.section",
                columns=(),
            ),
        ),
        builtin=False,
    )

    monkeypatch.setattr(reports, "get_template", lambda template_id, store=None: template)
    monkeypatch.setattr(
        reports,
        "ReportContext",
        lambda owner, start=None, end=None: SimpleNamespace(
            summary=lambda: reports.ReportData(
                owner=owner,
                start=None,
                end=None,
                realized_gains_gbp=0.0,
                income_gbp=0.0,
                cumulative_return=None,
                max_drawdown=None,
            ),
        ),
    )

    with caplog.at_level("WARNING", logger=reports.logger.name):
        document = reports.build_report_document("custom", "alice")

    assert document.sections[0].rows == ()
    assert "No builder registered" in caplog.text


def test_section_to_dataframe_includes_missing_columns():
    schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        columns=(
            reports.ReportColumnSchema("metric", "Metric"),
            reports.ReportColumnSchema("value", "Value"),
            reports.ReportColumnSchema("units", "Units"),
        ),
    )
    section = reports.ReportSectionData(
        schema=schema,
        rows=({"metric": "Owner", "value": "alice"},),
    )

    df = reports._section_to_dataframe(section)

    assert list(df.columns) == ["Metric", "Value", "Units"]
    assert df.iloc[0].to_dict() == {"Metric": "Owner", "Value": "alice", "Units": None}


def test_section_to_dataframe_empty_creates_headers():
    schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        columns=(
            reports.ReportColumnSchema("metric", "Metric"),
            reports.ReportColumnSchema("value", "Value"),
        ),
    )
    section = reports.ReportSectionData(schema=schema, rows=())

    df = reports._section_to_dataframe(section)

    assert df.empty
    assert list(df.columns) == ["Metric", "Value"]


def test_report_to_csv_includes_metadata(tmp_path):
    schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        columns=(
            reports.ReportColumnSchema("metric", "Metric"),
            reports.ReportColumnSchema("value", "Value"),
        ),
    )
    template = reports.ReportTemplate(
        template_id="example",
        name="Example",
        description="",
        sections=(schema,),
        builtin=True,
    )
    section = reports.ReportSectionData(
        schema=schema,
        rows=(
            {"metric": "Owner", "value": "alice"},
            {"metric": "Transactions", "value": 2},
        ),
    )
    document = reports.ReportDocument(
        template=template,
        owner="alice",
        generated_at=datetime.now(tz=reports.UTC),
        parameters={"start": "2024-01-01"},
        sections=(section,),
    )

    csv_bytes = reports.report_to_csv(document)
    content = csv_bytes.decode("utf-8")

    assert "Template: Example" in content
    assert "start: 2024-01-01" in content
    assert "Metric,Value" in content


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-01-01", date(2024, 1, 1)),
        ("invalid", None),
        (None, None),
    ],
)
def test_parse_date_handles_invalid_values(value, expected):
    assert reports._parse_date(value) == expected


def test_transaction_roots_local(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    transactions_dir = data_root / "transactions"
    transactions_dir.mkdir()

    output_root = tmp_path / "output"
    output_root.mkdir()
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()

    monkeypatch.setattr(reports.config, "app_env", "local", raising=False)
    monkeypatch.setattr(reports.config, "transactions_output_root", output_root, raising=False)
    monkeypatch.setattr(reports.config, "accounts_root", accounts_root, raising=False)
    monkeypatch.setattr(reports.config, "data_root", data_root, raising=False)

    roots = list(reports._transaction_roots())

    assert output_root.as_posix() in roots
    assert accounts_root.as_posix() in roots
    assert transactions_dir.as_posix() in roots


def test_build_key_findings_section_parses_valid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)
    owner_dir = tmp_path / "accounts" / "demo-owner"
    owner_dir.mkdir(parents=True)
    (owner_dir / "key_findings.md").write_text(
        "- Portfolio concentration is 42% in US tech versus 18% benchmark\n"
        "2. Cash drag is 6.4% above the 2.0% target corridor\n",
        encoding="utf-8",
    )

    context = reports.ReportContext("demo-owner", start=None, end=None)
    schema = reports.ReportSectionSchema(
        id="key-findings",
        title="Key Findings",
        source="portfolio.key_findings",
        columns=(reports.ReportColumnSchema("finding", "Finding"),),
    )

    rows = reports._build_key_findings_section(context, schema)

    assert rows == [
        {"finding": "Portfolio concentration is 42% in US tech versus 18% benchmark"},
        {"finding": "Cash drag is 6.4% above the 2.0% target corridor"},
    ]


def test_build_key_findings_section_returns_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)

    context = reports.ReportContext("demo-owner", start=None, end=None)
    schema = reports.ReportSectionSchema(
        id="key-findings",
        title="Key Findings",
        source="portfolio.key_findings",
        columns=(reports.ReportColumnSchema("finding", "Finding"),),
    )

    assert reports._build_key_findings_section(context, schema) == []


def test_build_key_findings_section_skips_invalid_lines_with_error(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)
    owner_dir = tmp_path / "accounts" / "demo-owner"
    owner_dir.mkdir(parents=True)
    (owner_dir / "key_findings.md").write_text(
        "- No ISA allowance used.\n"
        "- Portfolio concentration is 42% in US tech versus 18% benchmark\n"
        "- Portfolio is heavily concentrated in US large-cap growth stocks\n"
        f"- {'9' * 501}\n",
        encoding="utf-8",
    )

    context = reports.ReportContext("demo-owner", start=None, end=None)
    schema = reports.ReportSectionSchema(
        id="key-findings",
        title="Key Findings",
        source="portfolio.key_findings",
        columns=(reports.ReportColumnSchema("finding", "Finding"),),
    )

    with caplog.at_level("ERROR", logger=reports.logger.name):
        rows = reports._build_key_findings_section(context, schema)

    assert rows == [
        {"finding": "No ISA allowance used."},
        {"finding": "Portfolio concentration is 42% in US tech versus 18% benchmark"},
        {"finding": "Portfolio is heavily concentrated in US large-cap growth stocks"},
    ]
    assert "Skipping invalid key finding from key_findings.md because it exceeds 500 characters" in caplog.text


def test_build_key_findings_section_accepts_exactly_500_chars(tmp_path, monkeypatch):
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)
    owner_dir = tmp_path / "accounts" / "demo-owner"
    owner_dir.mkdir(parents=True)
    exact_limit_finding = "9" * 500
    (owner_dir / "key_findings.md").write_text(
        f"- {exact_limit_finding}\n",
        encoding="utf-8",
    )

    context = reports.ReportContext("demo-owner", start=None, end=None)
    schema = reports.ReportSectionSchema(
        id="key-findings",
        title="Key Findings",
        source="portfolio.key_findings",
        columns=(reports.ReportColumnSchema("finding", "Finding"),),
    )

    rows = reports._build_key_findings_section(context, schema)

    assert rows == [{"finding": exact_limit_finding}]


def test_build_key_findings_section_skips_empty_entries_after_trimming(tmp_path, monkeypatch):
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)
    owner_dir = tmp_path / "accounts" / "demo-owner"
    owner_dir.mkdir(parents=True)
    (owner_dir / "key_findings.md").write_text(
        "- \n"
        "* \n"
        "2.   \n"
        "- ok\n",
        encoding="utf-8",
    )

    context = reports.ReportContext("demo-owner", start=None, end=None)
    schema = reports.ReportSectionSchema(
        id="key-findings",
        title="Key Findings",
        source="portfolio.key_findings",
        columns=(reports.ReportColumnSchema("finding", "Finding"),),
    )

    rows = reports._build_key_findings_section(context, schema)

    assert rows == [{"finding": "ok"}]


def test_build_key_findings_section_reads_txt_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)
    owner_dir = tmp_path / "accounts" / "demo-owner"
    owner_dir.mkdir(parents=True)
    (owner_dir / "key_findings.txt").write_text(
        "1. Cash drag is 6.4% above the 2.0% target corridor\n",
        encoding="utf-8",
    )

    context = reports.ReportContext("demo-owner", start=None, end=None)
    schema = reports.ReportSectionSchema(
        id="key-findings",
        title="Key Findings",
        source="portfolio.key_findings",
        columns=(reports.ReportColumnSchema("finding", "Finding"),),
    )

    rows = reports._build_key_findings_section(context, schema)

    assert rows == [
        {"finding": "Cash drag is 6.4% above the 2.0% target corridor"}
    ]


def test_key_findings_source_is_registered_for_template_validation():
    payload = {
        "template_id": "custom-findings",
        "name": "Custom Findings",
        "description": "",
        "sections": [
            {
                "id": "key-findings",
                "title": "Key Findings",
                "source": "portfolio.key_findings",
                "columns": [{"key": "finding", "label": "Finding"}],
            }
        ],
    }

    result = reports._validate_template_payload(payload)

    assert result["sections"][0]["source"] == "portfolio.key_findings"


def test_build_report_document_omits_empty_key_findings_section(monkeypatch):
    template = reports.ReportTemplate(
        template_id="audit-report",
        name="Audit",
        description="",
        sections=(
            reports.ReportSectionSchema(
                id="metrics",
                title="Metrics",
                source="performance.metrics",
                columns=(
                    reports.ReportColumnSchema("metric", "Metric"),
                    reports.ReportColumnSchema("value", "Value"),
                    reports.ReportColumnSchema("units", "Units"),
                ),
            ),
            reports.ReportSectionSchema(
                id="key-findings",
                title="Key Findings",
                source="portfolio.key_findings",
                columns=(reports.ReportColumnSchema("finding", "Finding"),),
            ),
        ),
    )

    monkeypatch.setattr(reports, "get_template", lambda template_id, store=None: template)
    monkeypatch.setattr(
        reports,
        "ReportContext",
        lambda owner, start=None, end=None: SimpleNamespace(
            summary=lambda: reports.ReportData(
                owner=owner,
                start=None,
                end=None,
                realized_gains_gbp=0.0,
                income_gbp=0.0,
                cumulative_return=None,
                max_drawdown=None,
            ),
            transactions=lambda: [],
            allocation=lambda: [],
        ),
    )
    monkeypatch.setitem(
        reports.SECTION_BUILDERS,
        "portfolio.key_findings",
        lambda context, section: [],
    )

    document = reports.build_report_document("audit-report", "demo-owner")

    assert [section.schema.id for section in document.sections] == ["metrics"]


def test_audit_template_is_registered_with_expected_sections():
    template = reports.BUILTIN_TEMPLATES.get("audit-report")

    assert template is not None
    assert template.builtin is True
    assert [section.id for section in template.sections] == [
        "portfolio-overview",
        "true-exposure-sector",
        "true-exposure-region",
        "concentration-risk",
        "risk-assessment",
        "key-findings",
    ]
    assert [section.source for section in template.sections] == [
        "portfolio.overview",
        "portfolio.sectors",
        "portfolio.regions",
        "portfolio.concentration",
        "portfolio.var",
        "portfolio.key_findings",
    ]


def test_audit_template_sources_are_all_registered():
    template = reports.BUILTIN_TEMPLATES["audit-report"]
    missing = [
        section.source
        for section in template.sections
        if section.source not in reports.SECTION_BUILDERS
    ]
    assert missing == []


def test_audit_template_builders_render_non_empty_rows(monkeypatch, caplog):
    monkeypatch.setattr(
        reports.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, pricing_date=None: {
            "owner": owner,
            "total_value_estimate_gbp": 200.0,
            "accounts": [
                {
                    "account_type": "ISA",
                    "value_estimate_gbp": 200.0,
                    "holdings": [
                        {"ticker": "AAA.L", "asset_class": "Equity", "market_value_gbp": 120.0},
                        {"ticker": "BBB.L", "asset_class": "Equity", "market_value_gbp": 80.0},
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_sector",
        lambda portfolio: [
            {
                "sector": "Technology",
                "market_value_gbp": 120.0,
                "gain_gbp": 12.0,
                "cost_gbp": 108.0,
                "gain_pct": 0.1111,
                "contribution_pct": 0.6,
            },
            {
                "sector": "Healthcare",
                "market_value_gbp": 80.0,
                "gain_gbp": 8.0,
                "cost_gbp": 72.0,
                "gain_pct": 0.1111,
                "contribution_pct": 0.4,
            },
        ],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_region",
        lambda portfolio: [
            {
                "region": "North America",
                "market_value_gbp": 150.0,
                "gain_gbp": 15.0,
                "cost_gbp": 135.0,
                "gain_pct": 0.1111,
                "contribution_pct": 0.75,
            },
            {
                "region": "Europe",
                "market_value_gbp": 50.0,
                "gain_gbp": 5.0,
                "cost_gbp": 45.0,
                "gain_pct": 0.1111,
                "contribution_pct": 0.25,
            },
        ],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_ticker",
        lambda portfolio: [
            {"ticker": "AAA.L", "market_value_gbp": 120.0},
            {"ticker": "BBB.L", "market_value_gbp": 80.0},
        ],
    )
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence, include_cash=True: {
            "confidence": confidence,
            "1d": 12.34 if confidence == 0.95 else 18.76,
            "10d": 39.01 if confidence == 0.95 else 59.52,
        },
    )
    monkeypatch.setattr(reports.risk, "compute_sharpe_ratio", lambda owner: 1.23)

    with caplog.at_level("WARNING", logger=reports.logger.name):
        document = reports.build_report_document("audit-report", "alice")

    assert "No builder registered" not in caplog.text
    assert all(section.rows for section in document.sections)

    csv_content = reports.report_to_csv(document).decode("utf-8")
    assert "Sharpe ratio" in csv_content
    assert "Technology" in csv_content
    assert "AAA.L" in csv_content


def test_audit_risk_section_includes_var_and_sharpe(monkeypatch):
    monkeypatch.setattr(
        reports,
        "risk",
        SimpleNamespace(
            compute_portfolio_var=lambda owner, confidence, include_cash=True: {
                "confidence": confidence,
                "1d": 12.34 if confidence == 0.95 else 18.76,
                "10d": 39.01 if confidence == 0.95 else 59.52,
            },
            compute_sharpe_ratio=lambda owner: 1.23,
        ),
    )
    monkeypatch.setattr(
        reports,
        "portfolio_mod",
        SimpleNamespace(
            build_owner_portfolio=lambda owner, pricing_date=None: {"accounts": []}
        ),
    )

    rows = reports._build_portfolio_var_section(
        reports.ReportContext(owner="alice", start=None, end=None),
        reports.ReportSectionSchema(
            id="risk-assessment",
            title="Risk assessment (VaR/Sharpe)",
            source="portfolio.var",
            columns=(),
        ),
    )

    metrics = {row["metric"] for row in rows}
    assert "Sharpe ratio" in metrics
    assert [row["metric"] for row in rows] == ["VaR (95%)", "VaR (99%)", "Sharpe ratio"]


def test_build_report_document_omits_empty_var_section_for_audit_report(monkeypatch, tmp_path):
    """VaR section must be omitted from audit-report when the risk module is unavailable."""
    monkeypatch.setattr(reports, "risk", None)
    monkeypatch.setattr(reports, "_load_transactions", lambda owner: [])
    monkeypatch.setattr(
        reports,
        "_compile_summary",
        lambda owner, start, end: (
            reports.ReportData(
                owner=owner,
                start=None,
                end=None,
                realized_gains_gbp=0.0,
                income_gbp=0.0,
                cumulative_return=None,
                max_drawdown=None,
            ),
            {},
        ),
    )
    monkeypatch.setattr(
        reports.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, pricing_date=None: {"total_value_estimate_gbp": 0.0, "accounts": []},
    )
    monkeypatch.setattr(
        reports.portfolio_utils, "aggregate_by_sector", lambda portfolio: []
    )
    monkeypatch.setattr(
        reports.portfolio_utils, "aggregate_by_region", lambda portfolio: []
    )
    monkeypatch.setattr(
        reports.portfolio_utils, "aggregate_by_ticker", lambda portfolio: []
    )
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)

    document = reports.build_report_document("audit-report", "alice")

    var_sections = [s for s in document.sections if s.schema.source == "portfolio.var"]
    assert var_sections == [], "VaR section must be omitted when risk module is None"


def test_build_report_document_fails_for_builtin_missing_builder(monkeypatch):
    template = reports.ReportTemplate(
        template_id="builtin-broken",
        name="Broken",
        description="",
        sections=(
            reports.ReportSectionSchema(
                id="mystery",
                title="Mystery",
                source="unknown.section",
                columns=(),
            ),
        ),
        builtin=True,
    )
    monkeypatch.setattr(reports, "get_template", lambda template_id, store=None: template)
    monkeypatch.setattr(
        reports,
        "ReportContext",
        lambda owner, start=None, end=None: SimpleNamespace(
            summary=lambda: reports.ReportData(
                owner=owner,
                start=None,
                end=None,
                realized_gains_gbp=0.0,
                income_gbp=0.0,
                cumulative_return=None,
                max_drawdown=None,
            ),
        ),
    )

    with pytest.raises(ValueError, match="references unsupported source"):
        reports.build_report_document("builtin-broken", "alice")


def test_audit_report_template_has_key_findings_as_final_section():
    template = reports.get_template("audit-report")

    assert template is not None
    assert template.sections[-1].id == "key-findings"
    assert template.sections[-1].source == "portfolio.key_findings"
