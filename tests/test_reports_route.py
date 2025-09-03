import pytest
from fastapi.testclient import TestClient
import backend.reports as reports
from backend.app import create_app
from backend.reports import ReportData
from backend.routes import reports as reports_route


@pytest.fixture
def client():
    """Return an authenticated TestClient with reports router included."""
    from backend.app import create_app

    app = create_app()
    app.include_router(reports_route.router)

    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def sample_report():
    return reports.ReportData(
        owner="lucy",        start=None,
        end=None,
        realized_gains_gbp=10.0,
        income_gbp=5.0,
        cumulative_return=0.1,
        max_drawdown=-0.02,
    )


def test_reports_json(client, sample_report, monkeypatch):
    def fake_compile(owner, start=None, end=None):
        return sample_report

    monkeypatch.setattr(reports_route, "compile_report", fake_compile)
    resp = client.get("/reports/lucy")
    assert resp.status_code == 200
    assert resp.json() == sample_report.to_dict()


def test_reports_csv(client, sample_report, monkeypatch):
    def fake_compile(owner, start=None, end=None):
        return sample_report

    def fake_csv(data):
        return b"csv-data"

    monkeypatch.setattr(reports_route, "compile_report", fake_compile)
    monkeypatch.setattr(reports_route, "report_to_csv", fake_csv)

    resp = client.get("/reports/lucy?format=csv")
    assert resp.status_code == 200
    assert resp.content == b"csv-data"
    assert resp.headers["content-type"].startswith("text/csv")


def test_reports_pdf(client, sample_report, monkeypatch):
    def fake_compile(owner, start=None, end=None):
        return sample_report

    def fake_pdf(data):
        return b"%PDF-1.4 test"

    monkeypatch.setattr(reports_route, "compile_report", fake_compile)
    monkeypatch.setattr(reports_route, "report_to_pdf", fake_pdf)

    resp = client.get("/reports/lucy?format=pdf")
    assert resp.status_code == 200
    assert resp.content == b"%PDF-1.4 test"
    assert resp.headers["content-type"] == "application/pdf"


def test_reports_unknown_owner(client, monkeypatch):
    def fake_compile(owner, start=None, end=None):
        raise FileNotFoundError

    monkeypatch.setattr(reports_route, "compile_report", fake_compile)
    resp = client.get("/reports/lucy")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Owner not found"}
