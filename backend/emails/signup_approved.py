"""User-facing "your login is ready" email for approved signup requests.

Reuses the SES pattern established in :mod:`backend.emails.weekly_report`
(``boto3.client("ses")`` and the ``WEEKLY_REPORT_FROM`` sender). Sent to the
requesting visitor after an admin approves their access request (#4352).

The visitor-supplied name is HTML-escaped before being placed in the body so a
hostile name cannot inject markup into the recipient's inbox.
"""

from __future__ import annotations

import logging
import os

import boto3
from markupsafe import escape

logger = logging.getLogger(__name__)

_SENDER_EMAIL = os.getenv("WEEKLY_REPORT_FROM", "no-reply@allotmint.com")


def render_signup_approved_email(name: str, login_url: str) -> str:
    """Render the "login ready" HTML, escaping all visitor input."""

    greeting = f"Hi {escape(name)}," if name else "Hi,"
    if login_url:
        action = f'<p><a href="{escape(login_url)}">Log in to AllotMint</a></p>'
    else:
        action = "<p>You can now log in to AllotMint.</p>"
    return (
        "<html><body>"
        f"<p>{greeting}</p>"
        "<h2>Your AllotMint login is ready</h2>"
        "<p>Your access request has been approved. You can now sign in with "
        "this email address.</p>"
        f"{action}"
        "</body></html>"
    )


def send_signup_approved_email(user_email: str, name: str, login_url: str) -> None:
    """Send the "login ready" email via AWS SES.

    Any SES failure propagates to the caller so the route can decide how to
    surface it — the user has already been provisioned by this point, so the
    caller must not let a delivery failure silently undo that.
    """

    body_html = render_signup_approved_email(name, login_url)
    subject = "Your AllotMint login is ready"

    ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
    ses.send_email(
        Source=_SENDER_EMAIL,
        Destination={"ToAddresses": [user_email]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Html": {"Data": body_html}},
        },
    )
