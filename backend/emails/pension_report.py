from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import boto3
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

# Directory containing HTML templates
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Jinja2 environment for rendering email templates
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


@dataclass
class PensionReport:
    """Data required to render a pension report email."""

    owner_name: str
    stats: Dict[str, str]
    scenarios: List[Dict[str, str]]
    alerts: List[str] = field(default_factory=list)


def render_pension_report(report: PensionReport) -> str:
    """Render the pension report email HTML from a template."""

    template = _env.get_template("pension_report.html")
    return template.render(
        owner_name=report.owner_name,
        stats=report.stats,
        scenarios=report.scenarios,
        alerts=report.alerts,
    )


_SENDER_EMAIL = os.getenv("PENSION_REPORT_FROM", "no-reply@allotmint.com")


def send_pension_report_email(user_email: str, report: PensionReport) -> None:
    """Send the pension report email via AWS SES."""

    body_html = render_pension_report(report)
    subject = f"Pension Report - {report.owner_name}"

    ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
    ses.send_email(
        Source=_SENDER_EMAIL,
        Destination={"ToAddresses": [user_email]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Html": {"Data": body_html}},
        },
    )
