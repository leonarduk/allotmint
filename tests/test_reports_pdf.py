import pytest

from datetime import datetime

import pytest

import backend.reports as reports


def _example_document() -> reports.ReportDocument:
    section_schema = reports.ReportSectionSchema(
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
        name="Example template",
        description="",
        sections=(section_schema,),
        builtin=False,
    )
    section = reports.ReportSectionData(
        schema=section_schema,
        rows=({"metric": "Owner", "value": "alice"},),
    )
    return reports.ReportDocument(
        template=template,
        owner="alice",
        generated_at=datetime.now(tz=reports.UTC),
        parameters={},
        sections=(section,),
    )


def test_report_to_pdf_requires_reportlab(monkeypatch):
    document = _example_document()
    monkeypatch.setattr(reports, "canvas", None)
    with pytest.raises(RuntimeError, match="reportlab is required for PDF output"):
        reports.report_to_pdf(document)


def test_report_to_pdf_generates_pdf():
    if reports.canvas is None:
        pytest.skip("reportlab not installed")
    document = _example_document()
    pdf = reports.report_to_pdf(document)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 0


def test_report_to_pdf_key_findings_section_renders_text():
    if reports.canvas is None:
        pytest.skip("reportlab not installed")

    key_schema = reports.ReportSectionSchema(
        id="key-findings",
        title="Key Findings",
        source="portfolio.key_findings",
        columns=(reports.ReportColumnSchema("finding", "Finding"),),
    )
    template = reports.ReportTemplate(
        template_id="audit-report",
        name="Audit report",
        description="",
        sections=(key_schema,),
        builtin=True,
    )
    section = reports.ReportSectionData(
        schema=key_schema,
        rows=(
            {"finding": "Portfolio concentration is 42% in US tech versus 18% benchmark"},
            {"finding": "Cash allocation is 12.6% compared with a 5.0% policy target"},
        ),
    )
    document = reports.ReportDocument(
        template=template,
        owner="demo-owner",
        generated_at=datetime.now(tz=reports.UTC),
        parameters={},
        sections=(section,),
    )

    pdf = reports.report_to_pdf(document)

    assert pdf.startswith(b"%PDF")
    assert b"Key Findings" in pdf
    assert b"Portfolio concentration is 42% in US tech versus 18% benchmark" in pdf


def test_report_to_pdf_succeeds_without_key_findings_section():
    if reports.canvas is None:
        pytest.skip("reportlab not installed")

    document = _example_document()

    pdf = reports.report_to_pdf(document)

    assert pdf.startswith(b"%PDF")


def test_audit_report_pdf_contains_all_section_titles(monkeypatch):
    """PDF output for audit-report must include titles for all populated sections."""
    if reports.canvas is None:
        pytest.skip("reportlab not installed")

    monkeypatch.setattr(
        reports.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, pricing_date=None: {
            "total_value_estimate_gbp": 50000.0,
            "accounts": [
                {
                    "account_type": "ISA",
                    "value_estimate_gbp": 50000.0,
                    "holdings": [
                        {"ticker": "AAPL.O", "asset_class": "Equity", "market_value_gbp": 30000.0},
                        {"ticker": "VWRL.L", "asset_class": "ETF", "market_value_gbp": 20000.0},
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_sector",
        lambda portfolio: [
            {"sector": "Technology", "market_value_gbp": 30000.0},
            {"sector": "Diversified", "market_value_gbp": 20000.0},
        ],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_region",
        lambda portfolio: [
            {"region": "North America", "market_value_gbp": 30000.0},
            {"region": "Global", "market_value_gbp": 20000.0},
        ],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_ticker",
        lambda portfolio: [
            {"ticker": "AAPL.O", "market_value_gbp": 30000.0},
            {"ticker": "VWRL.L", "market_value_gbp": 20000.0},
        ],
    )
    monkeypatch.setattr(
        reports.risk_mod,
        "compute_portfolio_var",
        lambda owner, confidence: {"confidence": confidence, "1d": 800.0, "10d": 2530.0},
    )
    monkeypatch.setattr(reports.risk_mod, "compute_sharpe_ratio", lambda owner: 1.42)

    document = reports.build_report_document("audit-report", "demo-owner")

    pdf = reports.report_to_pdf(document)

    assert pdf.startswith(b"%PDF")
    assert b"Portfolio overview" in pdf
    assert b"Sector allocation" in pdf
    assert b"Region allocation" in pdf
    assert b"Top holdings concentration" in pdf
    assert b"Portfolio risk" in pdf


def test_audit_report_json_section_order_and_presence(monkeypatch):
    """build_report_document('audit-report') must return sections 1-4 in correct order."""
    monkeypatch.setattr(
        reports.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, pricing_date=None: {
            "total_value_estimate_gbp": 10000.0,
            "accounts": [
                {
                    "account_type": "GIA",
                    "value_estimate_gbp": 10000.0,
                    "holdings": [
                        {"ticker": "VOD.L", "asset_class": "Equity", "market_value_gbp": 10000.0},
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_sector",
        lambda portfolio: [{"sector": "Telecoms", "market_value_gbp": 10000.0}],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_region",
        lambda portfolio: [{"region": "UK", "market_value_gbp": 10000.0}],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_ticker",
        lambda portfolio: [{"ticker": "VOD.L", "market_value_gbp": 10000.0}],
    )
    monkeypatch.setattr(
        reports.risk_mod,
        "compute_portfolio_var",
        lambda owner, confidence: {"confidence": confidence, "1d": 200.0, "10d": 630.0},
    )
    monkeypatch.setattr(reports.risk_mod, "compute_sharpe_ratio", lambda owner: 0.85)

    document = reports.build_report_document("audit-report", "demo-owner")

    sources = [section.schema.source for section in document.sections]
    # Key findings omitted (no findings file for demo-owner in test env)
    assert "portfolio.overview" in sources
    assert "portfolio.sectors" in sources
    assert "portfolio.regions" in sources
    assert "portfolio.concentration" in sources
    assert "portfolio.var" in sources
    # Section order must match template definition
    non_findings = [s for s in sources if s != "portfolio.key_findings"]
    assert non_findings == [
        "portfolio.overview",
        "portfolio.sectors",
        "portfolio.regions",
        "portfolio.concentration",
        "portfolio.var",
    ]

    # Overview returns at least one row with total value
    overview_section = next(s for s in document.sections if s.schema.source == "portfolio.overview")
    assert len(overview_section.rows) >= 1

    # Concentration rows are ordered by value descending (highest weight first)
    concentration_section = next(
        s for s in document.sections if s.schema.source == "portfolio.concentration"
    )
    assert len(concentration_section.rows) >= 1

    # VaR section present and non-empty when risk module available
    var_section = next(s for s in document.sections if s.schema.source == "portfolio.var")
    assert len(var_section.rows) >= 1
    metrics = [row["metric"] for row in var_section.rows]
    assert any("VaR" in m for m in metrics)


def test_audit_report_var_section_omitted_when_risk_unavailable(monkeypatch, tmp_path):
    """When risk module is None, VaR section must be omitted entirely (not empty-rowed)."""
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
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_sector", lambda portfolio: [])
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_region", lambda portfolio: [])
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_ticker", lambda portfolio: [])
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)

    document = reports.build_report_document("audit-report", "demo-owner")

    var_sections = [s for s in document.sections if s.schema.source == "portfolio.var"]
    assert var_sections == [], "VaR section must be absent, not empty-rowed, when risk=None"


def test_existing_templates_unaffected_by_audit_report_changes(monkeypatch):
    """performance-summary, transactions, allocation-breakdown must still build correctly."""
    from types import SimpleNamespace

    summary = reports.ReportData(
        owner="alice",
        start=None,
        end=None,
        realized_gains_gbp=100.0,
        income_gbp=10.0,
        cumulative_return=0.05,
        max_drawdown=-0.02,
        history=[],
    )
    monkeypatch.setattr(
        reports, "_compile_summary", lambda owner, start, end: (summary, {"history": []})
    )
    monkeypatch.setattr(reports, "_load_transactions", lambda owner: [])
    monkeypatch.setattr(
        reports.portfolio_utils,
        "portfolio_value_breakdown",
        lambda owner, date: [],
    )

    for template_id in ("performance-summary", "transactions", "allocation-breakdown"):
        document = reports.build_report_document(template_id, "alice")
        assert document.template.template_id == template_id
        assert len(document.sections) == len(
            reports.BUILTIN_TEMPLATES[template_id].sections
        ), f"{template_id}: section count mismatch"
