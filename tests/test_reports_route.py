from datetime import datetime
from typing import Dict

import pytest
from fastapi.testclient import TestClient

import backend.reports as reports
from backend.routes import reports as reports_route


def _build_sample_document() -> reports.ReportDocument:
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
        rows=({"metric": "Owner", "value": "lucy"},),
    )
    return reports.ReportDocument(
        template=template,
        owner="lucy",
        generated_at=datetime.now(tz=reports.UTC),
        parameters={},
        sections=(section,),
    )


def _sample_template(template_id: str = "custom") -> Dict[str, object]:
    return {
        "template_id": template_id,
        "name": "Custom",
        "description": "",
        "builtin": False,
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "description": None,
                "source": "performance.metrics",
                "columns": [
                    {"key": "metric", "label": "Metric", "type": "string"},
                    {"key": "value", "label": "Value", "type": "string"},
                ],
            }
        ],
    }


@pytest.fixture
def client():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(reports_route.router)

    return TestClient(app)


def test_reports_json(client, monkeypatch):
    document = _build_sample_document()

    monkeypatch.setattr(
        reports_route,
        "build_report_document",
        lambda template_id, owner, start=None, end=None: document,
    )

    resp = client.get("/reports/lucy")
    assert resp.status_code == 200
    assert resp.json()["template"]["template_id"] == "example"


def test_reports_csv(client, monkeypatch):
    document = _build_sample_document()

    monkeypatch.setattr(
        reports_route,
        "build_report_document",
        lambda template_id, owner, start=None, end=None: document,
    )
    monkeypatch.setattr(reports_route, "report_to_csv", lambda doc: b"csv-data")

    resp = client.get("/reports/lucy?format=csv")
    assert resp.status_code == 200
    assert resp.content == b"csv-data"
    assert resp.headers["content-type"].startswith("text/csv")


def test_reports_pdf(client, monkeypatch):
    document = _build_sample_document()

    monkeypatch.setattr(
        reports_route,
        "build_report_document",
        lambda template_id, owner, start=None, end=None: document,
    )
    monkeypatch.setattr(reports_route, "report_to_pdf", lambda doc: b"%PDF-test")

    resp = client.get("/reports/lucy?format=pdf")
    assert resp.status_code == 200
    assert resp.content == b"%PDF-test"
    assert resp.headers["content-type"] == "application/pdf"


def test_reports_unknown_owner(client, monkeypatch):
    def fake_builder(template_id, owner, start=None, end=None):
        raise FileNotFoundError

    monkeypatch.setattr(reports_route, "build_report_document", fake_builder)

    resp = client.get("/reports/lucy")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Owner not found"}


def test_owner_template_report(client, monkeypatch):
    document = _build_sample_document()
    monkeypatch.setattr(
        reports_route,
        "build_report_document",
        lambda template_id, owner, start=None, end=None: document,
    )

    resp = client.get("/reports/lucy/transactions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["template"]["template_id"] == "example"


def test_list_templates_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        reports_route,
        "list_template_metadata",
        lambda: [_sample_template("performance-summary"), _sample_template()],
    )
    resp = client.get("/reports/templates")
    assert resp.status_code == 200
    assert resp.json()[0]["template_id"] == "performance-summary"


def test_get_template_definition(client, monkeypatch):
    monkeypatch.setattr(
        reports_route,
        "get_template",
        lambda template_id: reports.ReportTemplate(
            template_id=template_id,
            name="Example",
            description="",
            sections=(),
            builtin=True,
        ),
    )

    resp = client.get("/reports/templates/performance-summary")
    assert resp.status_code == 200
    assert resp.json()["template_id"] == "performance-summary"


def test_create_template_endpoint(client, monkeypatch):
    template = reports.ReportTemplate(
        template_id="custom",
        name="Custom",
        description="",
        sections=(),
        builtin=False,
    )
    monkeypatch.setattr(reports_route, "create_user_template", lambda payload: template)

    payload = {
        "template_id": "custom",
        "name": "Custom",
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "source": "performance.metrics",
                "columns": [
                    {"key": "metric", "label": "Metric", "type": "string"}
                ],
            }
        ],
    }
    resp = client.post("/reports/templates", json=payload)
    assert resp.status_code == 201
    assert resp.json()["template_id"] == "custom"


def test_update_template_endpoint(client, monkeypatch):
    template = reports.ReportTemplate(
        template_id="custom",
        name="Updated",
        description="",
        sections=(),
        builtin=False,
    )
    monkeypatch.setattr(reports_route, "update_user_template", lambda tid, payload: template)

    payload = {
        "name": "Updated",
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "source": "performance.metrics",
                "columns": [
                    {"key": "metric", "label": "Metric", "type": "string"}
                ],
            }
        ],
    }
    resp = client.put("/reports/templates/custom", json=payload)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


def test_delete_template_endpoint(client, monkeypatch):
    called = {}

    def fake_delete(template_id):
        called["template_id"] = template_id

    monkeypatch.setattr(reports_route, "delete_user_template", fake_delete)

    resp = client.delete("/reports/templates/custom")
    assert resp.status_code == 204
    assert called["template_id"] == "custom"
