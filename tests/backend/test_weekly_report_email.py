from unittest.mock import MagicMock, patch

import pandas as pd

from backend.emails.weekly_report import (
    WeeklyReport,
    render_weekly_report,
    send_weekly_report_email,
)


def test_render_weekly_report_renders_content():
    # BeautifulSoup normalises single-quoted HTML attributes to double-quoted, so
    # the assertions below use double quotes even though the fixture uses single quotes.
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
    assert '<table id="holdings"></table>' in html
    assert '<table id="tx"></table>' in html


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


def test_render_weekly_report_cell_values_are_sanitized_at_render_time():
    """HTML in DataFrame cell values is sanitized; the table structure is preserved."""
    xss_payload = "<script>alert('xss')</script>"
    df = pd.DataFrame({"owner": [xss_payload], "value": [100]})
    holdings_html = df.to_html(index=False, escape=False)
    transactions_html = df.to_html(index=False, escape=False)

    report = WeeklyReport(
        week_number=5,
        portfolio_stats={},
        holdings_table=holdings_html,
        transactions_table=transactions_html,
    )
    html = render_weekly_report(report)

    assert xss_payload not in html
    assert "alert('xss')" not in html
    assert "<table" in html


def test_render_weekly_report_strips_dangerous_table_attributes():
    report = WeeklyReport(
        week_number=5,
        portfolio_stats={},
        holdings_table='<table onclick="alert(1)" id="safe"><tr><td>holding</td></tr></table>',
        transactions_table='<table><tr><td><img src=x onerror="alert(1)">tx</td></tr></table>',
    )
    html = render_weekly_report(report)

    assert "onclick" not in html
    assert "onerror" not in html
    assert "<img" not in html
    assert 'id="safe"' in html
    assert "holding" in html
    assert "tx" in html


def test_render_weekly_report_strips_nested_disallowed_tags():
    """Disallowed tags nested inside other disallowed tags are both removed."""
    report = WeeklyReport(
        week_number=5,
        portfolio_stats={},
        holdings_table=(
            "<table><tr><td>"
            "<div><span onclick=\"evil()\">inner text</span></div>"
            "</td></tr></table>"
        ),
        transactions_table="<table></table>",
    )
    html = render_weekly_report(report)

    assert "<div" not in html
    assert "<span" not in html
    assert "onclick" not in html
    assert "inner text" in html
    assert "<table" in html
