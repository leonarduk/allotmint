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

