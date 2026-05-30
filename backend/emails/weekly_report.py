from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import boto3
from bs4 import BeautifulSoup, Comment
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

logger = logging.getLogger(__name__)

_ALLOWED_TABLE_TAGS = {"table", "thead", "tbody", "tfoot", "tr", "th", "td"}
# "border" is retained because pandas.DataFrame.to_html() emits border="1" by default.
# It is a presentational attribute with no scripting capability and is safe to keep.
_ALLOWED_TABLE_ATTRS = {"class", "id", "border"}

# Directory containing HTML templates
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Jinja2 environment for rendering email templates
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


@dataclass
class WeeklyReport:
    """Data required to render a weekly report email."""

    week_number: int
    portfolio_stats: Dict[str, str]
    holdings_table: str
    transactions_table: str


def _sanitize_table_html(table_html: str) -> Markup:
    """Strip all non-table tags and dangerous attributes from an HTML table string.

    Returns a ``markupsafe.Markup`` instance so Jinja2 renders the table
    structure as-is without double-escaping, while all scripting vectors have
    been removed.  Only tags in ``_ALLOWED_TABLE_TAGS`` and attributes in
    ``_ALLOWED_TABLE_ATTRS`` survive the pass.
    """

    soup = BeautifulSoup(table_html, "html.parser")
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()

    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    for tag in soup.find_all(True):
        if tag.name not in _ALLOWED_TABLE_TAGS:
            tag.unwrap()
            continue

        attrs = dict(tag.attrs)
        tag.attrs.clear()
        for attr, value in attrs.items():
            if attr in _ALLOWED_TABLE_ATTRS:
                tag.attrs[attr] = value

    return Markup(str(soup))


def render_weekly_report(report: WeeklyReport) -> str:
    """Render the weekly report email HTML from a template."""

    template = _env.get_template("weekly_report.html")
    return template.render(
        week_number=report.week_number,
        portfolio_stats=report.portfolio_stats,
        holdings_table=_sanitize_table_html(report.holdings_table),
        transactions_table=_sanitize_table_html(report.transactions_table),
    )


_SENDER_EMAIL = os.getenv("WEEKLY_REPORT_FROM", "no-reply@allotmint.com")


def send_weekly_report_email(user_email: str, report: WeeklyReport) -> None:
    """Send the weekly report email via AWS SES."""

    body_html = render_weekly_report(report)
    subject = f"Weekly Report - Week {report.week_number}"

    ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
    ses.send_email(
        Source=_SENDER_EMAIL,
        Destination={"ToAddresses": [user_email]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Html": {"Data": body_html}},
        },
    )
