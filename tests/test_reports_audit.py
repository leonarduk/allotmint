import json
from pathlib import Path

import pytest

import backend.reports as reports


def _demo_owner_portfolio_fixture() -> dict:
    fixture_path = Path(__file__).parent / "data" / "reports" / "demo_owner_portfolio_fixture.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def _patched_audit_report_dependencies(monkeypatch) -> dict:
    fixture_portfolio = _demo_owner_portfolio_fixture()

    monkeypatch.setattr(reports, "build_owner_portfolio", lambda owner: fixture_portfolio)
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence=0.95, include_cash=True: {
            "1d": 25.0 if confidence == 0.95 else 40.0
        },
    )
    monkeypatch.setattr(reports.risk, "compute_sharpe_ratio", lambda owner: 1.2)

    return fixture_portfolio


def _audit_rows_by_source() -> dict[str, list[dict]]:
    document = reports.build_report_document("audit-report", "demo-owner")
    return {section.schema.source: list(section.rows) for section in document.sections}


def test_audit_report_section_builders_use_fixture_rows(_patched_audit_report_dependencies, caplog):
    with caplog.at_level("WARNING", logger=reports.logger.name):
        rows_by_source = _audit_rows_by_source()

    assert "No builder registered" not in caplog.text
    assert "failed to build owner portfolio" not in caplog.text

    expected_sources = {
        "portfolio.overview",
        "portfolio.sectors",
        "portfolio.regions",
        "portfolio.concentration",
        "portfolio.var",
    }
    assert expected_sources.issubset(rows_by_source)

    assert len(rows_by_source["portfolio.overview"]) == 1
    assert len(rows_by_source["portfolio.sectors"]) == 2
    assert len(rows_by_source["portfolio.regions"]) == 2
    assert len(rows_by_source["portfolio.concentration"]) == 3
    assert len(rows_by_source["portfolio.var"]) == 3


def test_audit_report_rows_match_declared_column_keys(_patched_audit_report_dependencies):
    document = reports.build_report_document("audit-report", "demo-owner")

    expected_sources = {
        "portfolio.overview",
        "portfolio.sectors",
        "portfolio.regions",
        "portfolio.concentration",
        "portfolio.var",
    }
    sections_by_source = {section.schema.source: section for section in document.sections}

    assert expected_sources.issubset(sections_by_source)

    for source in expected_sources:
        section = sections_by_source[source]
        assert section.rows, f"section {source} unexpectedly empty"
        expected_keys = {column.key for column in section.schema.columns}
        for row in section.rows:
            assert set(row.keys()) == expected_keys


def test_audit_report_sector_and_region_rows_include_expected_aggregates(
    _patched_audit_report_dependencies,
):
    rows_by_source = _audit_rows_by_source()

    expected_sector_values = {
        "Technology": (700.0, 70.0),
        "Healthcare": (300.0, 30.0),
    }
    for row in rows_by_source["portfolio.sectors"]:
        expected_value, expected_weight = expected_sector_values[row["sector"]]
        assert row["value"] == expected_value
        assert row["weight"] * 100.0 == expected_weight

    expected_region_values = {
        "Europe": (600.0, 60.0),
        "North America": (400.0, 40.0),
    }
    for row in rows_by_source["portfolio.regions"]:
        expected_value, expected_weight = expected_region_values[row["region"]]
        assert row["value"] == expected_value
        assert row["weight"] * 100.0 == expected_weight
