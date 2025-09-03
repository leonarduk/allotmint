import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.reports import ReportData
from backend.routes import reports as reports_route


@pytest.fixture
def client():
    app = create_app()
    app.include_router(reports_route.router)
    return TestClient(app)


def _sample_report():
    return ReportData(
        owner="alice",
        start=None,
        end=None,
        realized_gains_gbp=10.0,
        income_gbp=5.0,
        cumulative_return=0.1,
        max_drawdown=-0.02,
    )


def test_report_json(client, monkeypatch):
    report = _sample_report()

    def fake_compile(owner, start=None, end=None):
        assert owner == "alice"
        return report

    monkeypatch.setattr("backend.routes.reports.compile_report", fake_compile)

    resp = client.get("/reports/alice")
    assert resp.status_code == 200
    assert resp.json() == report.to_dict()


def test_report_csv(client, monkeypatch):
    report = _sample_report()
    monkeypatch.setattr(
        "backend.routes.reports.compile_report",
        lambda owner, start=None, end=None: report,
    )
    monkeypatch.setattr(
        "backend.routes.reports.report_to_csv", lambda data: b"header\nvalue\n"
    )

    resp = client.get("/reports/alice?format=csv")
    assert resp.status_code == 200
    assert resp.content == b"header\nvalue\n"
    assert resp.headers["content-type"].startswith("text/csv")
    assert (
        resp.headers["content-disposition"]
        == "attachment; filename=alice_report.csv"
    )


def test_report_pdf(client, monkeypatch):
    report = _sample_report()
    monkeypatch.setattr(
        "backend.routes.reports.compile_report",
        lambda owner, start=None, end=None: report,
    )
    monkeypatch.setattr(
        "backend.routes.reports.report_to_pdf", lambda data: b"%PDF-1.4\n"
    )

    resp = client.get("/reports/alice?format=pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    assert resp.headers["content-type"].startswith("application/pdf")
    assert (
        resp.headers["content-disposition"]
        == "attachment; filename=alice_report.pdf"
    )


def test_report_unknown_owner(client, monkeypatch):
    def fake_compile(owner, start=None, end=None):
        raise FileNotFoundError

    monkeypatch.setattr("backend.routes.reports.compile_report", fake_compile)

    resp = client.get("/reports/unknown")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Owner not found"}
