import pytest

from backend.emails import weekly_report


def _sample_report() -> weekly_report.WeeklyReport:
    return weekly_report.WeeklyReport(
        week_number=42,
        portfolio_stats={"return": "5%"},
        holdings_table="<table>holdings</table>",
        transactions_table="<table>transactions</table>",
    )


def test_render_weekly_report_uses_template(monkeypatch):
    captured = {}

    class FakeTemplate:
        def render(self, **context):
            captured.update(context)
            return "<html>rendered</html>"

    monkeypatch.setattr(
        weekly_report._env,  # type: ignore[attr-defined]
        "get_template",
        lambda name: FakeTemplate(),
    )

    report = _sample_report()
    html = weekly_report.render_weekly_report(report)

    assert html == "<html>rendered</html>"
    assert captured == {
        "week_number": 42,
        "portfolio_stats": {"return": "5%"},
        "holdings_table": "<table>holdings</table>",
        "transactions_table": "<table>transactions</table>",
    }


def test_send_weekly_report_email(monkeypatch):
    sent = {}

    def fake_render(report):
        return "<html>body</html>"

    class StubSES:
        def send_email(self, **payload):
            sent.update(payload)

    monkeypatch.setattr(weekly_report, "render_weekly_report", fake_render)
    monkeypatch.setattr(weekly_report, "_SENDER_EMAIL", "reports@example.com", raising=False)
    monkeypatch.setattr(weekly_report.boto3, "client", lambda service, region_name=None: StubSES())

    weekly_report.send_weekly_report_email("user@example.com", _sample_report())

    assert sent["Source"] == "reports@example.com"
    assert sent["Destination"] == {"ToAddresses": ["user@example.com"]}
    assert sent["Message"]["Subject"]["Data"] == "Weekly Report - Week 42"
    assert sent["Message"]["Body"]["Html"]["Data"] == "<html>body</html>"
