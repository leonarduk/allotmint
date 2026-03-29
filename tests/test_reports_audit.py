import json
from pathlib import Path

import backend.reports as reports


def _demo_owner_portfolio_fixture() -> dict:
    fixture_path = Path(__file__).parent / "data" / "reports" / "demo_owner_portfolio_fixture.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_audit_report_section_builders_use_fixture_rows(monkeypatch, caplog):
    fixture_portfolio = _demo_owner_portfolio_fixture()

    monkeypatch.setattr(reports, "build_owner_portfolio", lambda owner: fixture_portfolio)
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence=0.95: {"1d": 25.0 if confidence == 0.95 else 40.0},
    )
    monkeypatch.setattr(reports.risk, "compute_sharpe_ratio", lambda owner: 1.2)

    with caplog.at_level("WARNING", logger=reports.logger.name):
        document = reports.build_report_document("audit-report", "demo-owner")

    rows_by_source = {section.schema.source: list(section.rows) for section in document.sections}

    assert "No builder registered" not in caplog.text
    assert "failed to build owner portfolio" not in caplog.text

    assert len(rows_by_source["portfolio.overview"]) == 1
    assert len(rows_by_source["portfolio.sectors"]) == 2
    assert len(rows_by_source["portfolio.regions"]) == 2
    assert len(rows_by_source["portfolio.concentration"]) == 3
    assert len(rows_by_source["portfolio.var"]) == 3


def test_audit_report_rows_match_declared_column_keys(monkeypatch):
    fixture_portfolio = _demo_owner_portfolio_fixture()

    monkeypatch.setattr(reports, "build_owner_portfolio", lambda owner: fixture_portfolio)
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence=0.95: {"1d": 25.0 if confidence == 0.95 else 40.0},
    )
    monkeypatch.setattr(reports.risk, "compute_sharpe_ratio", lambda owner: 1.2)

    document = reports.build_report_document("audit-report", "demo-owner")

    expected_sources = {
        "portfolio.overview",
        "portfolio.sectors",
        "portfolio.regions",
        "portfolio.concentration",
        "portfolio.var",
    }

    for section in document.sections:
        if section.schema.source not in expected_sources:
            continue

        assert section.rows, f"section {section.schema.source} unexpectedly empty"
        expected_keys = {column.key for column in section.schema.columns}
        for row in section.rows:
            assert set(row.keys()) == expected_keys
