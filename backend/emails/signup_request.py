"""Admin notification email for public account-signup requests.

Reuses the SES pattern established in :mod:`backend.emails.weekly_report`
(``boto3.client("ses")`` and the ``WEEKLY_REPORT_FROM`` sender). The recipient
is the admin address configured by the caller (``SIGNUP_ADMIN_EMAIL``).

All visitor-supplied fields are HTML-escaped before being placed in the email
body so a hostile name/note cannot inject markup into the admin's inbox.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import boto3
from markupsafe import escape

logger = logging.getLogger(__name__)

_SENDER_EMAIL = os.getenv("WEEKLY_REPORT_FROM", "no-reply@allotmint.com")


@dataclass
class SignupAdminNotification:
    """Data required to render the admin notification email."""

    request_id: str
    name: str
    email: str
    note: str
    approve_url: str
    reject_url: str
    expires_at: str


def render_signup_admin_email(notification: SignupAdminNotification) -> str:
    """Render the admin notification HTML, escaping all visitor input."""

    note_html = escape(notification.note) if notification.note else "<em>(none)</em>"
    return (
        "<html><body>"
        "<h2>New AllotMint access request</h2>"
        f"<p><strong>Name:</strong> {escape(notification.name)}</p>"
        f"<p><strong>Email:</strong> {escape(notification.email)}</p>"
        f"<p><strong>Note:</strong> {note_html}</p>"
        f"<p><strong>Request ID:</strong> {escape(notification.request_id)}</p>"
        "<p>"
        f'<a href="{escape(notification.approve_url)}">Approve</a>'
        " &nbsp;|&nbsp; "
        f'<a href="{escape(notification.reject_url)}">Reject</a>'
        "</p>"
        f"<p>These links expire at {escape(notification.expires_at)}.</p>"
        "</body></html>"
    )


def send_signup_admin_email(admin_email: str, notification: SignupAdminNotification) -> None:
    """Send the admin notification email via AWS SES.

    Any SES failure propagates to the caller — it must not be swallowed, so the
    route can surface the failure rather than silently dropping the request.
    """

    body_html = render_signup_admin_email(notification)
    subject = f"AllotMint access request from {notification.name}"

    ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
    ses.send_email(
        Source=_SENDER_EMAIL,
        Destination={"ToAddresses": [admin_email]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Html": {"Data": body_html}},
        },
    )
