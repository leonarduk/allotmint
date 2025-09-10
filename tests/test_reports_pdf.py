import pytest

import backend.reports as reports


def _example_report() -> reports.ReportData:
    return reports.ReportData(
        owner="alice",
        start=None,
        end=None,
        realized_gains_gbp=0.0,
        income_gbp=0.0,
        cumulative_return=None,
        max_drawdown=None,
    )


def test_report_to_pdf_requires_reportlab(monkeypatch):
    data = _example_report()
    monkeypatch.setattr(reports, "canvas", None)
    with pytest.raises(RuntimeError, match="reportlab is required for PDF output"):
        reports.report_to_pdf(data)


def test_report_to_pdf_generates_pdf():
    if reports.canvas is None:
        pytest.skip("reportlab not installed")
    data = _example_report()
    pdf = reports.report_to_pdf(data)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 0

