"""Email a plan-drift brief (#10475); same SES/Jinja2 pattern as ``pension_report``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import boto3
from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=select_autoescape(["html", "xml"]))

_SENDER_EMAIL = os.getenv("PLAN_BRIEF_FROM", os.getenv("PENSION_REPORT_FROM", "no-reply@allotmint.com"))


def render_plan_brief(brief: Mapping[str, Any], owner_name: str) -> str:
    return _env.get_template("plan_brief.html").render(brief=brief, owner_name=owner_name)


def send_plan_brief_email(user_email: str, brief: Mapping[str, Any], owner_name: str) -> None:
    """Send ``brief`` to ``user_email`` via AWS SES."""
    ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
    ses.send_email(
        Source=_SENDER_EMAIL,
        Destination={"ToAddresses": [user_email]},
        Message={
            "Subject": {"Data": f"Plan brief {brief.get('as_of')} - {owner_name}"},
            "Body": {"Html": {"Data": render_plan_brief(brief, owner_name)}},
        },
    )
