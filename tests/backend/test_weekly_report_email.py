from unittest.mock import MagicMock, patch

from backend.emails.weekly_report import (
    WeeklyReport,
    render_weekly_report,
    send_weekly_report_email,
)


def test_render_weekly_report_renders_content():
    report = WeeklyReport(
        week_number=42,
        portfolio_stats={"Return": "5%", "Value": "$1000"},
        holdings_table="<table id='holdings'></table>",
        transactions_table="<table id='tx'></table>",
    )
    html = render_weekly_report(report)
    assert "Week 42" in html
    for label, value in report.portfolio_stats.items():
        assert label in html
        assert value in html
    assert report.holdings_table in html
    assert report.transactions_table in html


def test_send_weekly_report_email_invokes_ses():
    report = WeeklyReport(week_number=1, portfolio_stats={}, holdings_table="", transactions_table="")
    rendered = "<html>body</html>"

    with patch("backend.emails.weekly_report.render_weekly_report", return_value=rendered) as render_mock:
        ses_client = MagicMock()
        with patch("boto3.client", return_value=ses_client):
            send_weekly_report_email("user@example.com", report)

    render_mock.assert_called_once_with(report)
    ses_client.send_email.assert_called_once()
    args, kwargs = ses_client.send_email.call_args
    assert kwargs["Destination"]["ToAddresses"] == ["user@example.com"]
    assert "Week 1" in kwargs["Message"]["Subject"]["Data"]
    assert kwargs["Message"]["Body"]["Html"]["Data"] == rendered
