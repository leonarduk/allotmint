from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, ParamValidationError

from backend.emails.signup_request import (
    SignupAdminNotification,
    render_signup_admin_email,
    send_signup_admin_email,
)


def _notification(**overrides) -> SignupAdminNotification:
    base = dict(
        request_id="abc123",
        name="Jane Doe",
        email="jane@example.com",
        note="please let me in",
        approve_url="https://admin.example.com/signup/approve?id=abc123&token=t",
        reject_url="https://admin.example.com/signup/reject?id=abc123&token=t",
        expires_at="2026-06-22T12:00:00+00:00",
    )
    base.update(overrides)
    return SignupAdminNotification(**base)


def test_render_includes_request_details_and_links():
    html = render_signup_admin_email(_notification())
    assert "Jane Doe" in html
    assert "jane@example.com" in html
    assert "please let me in" in html
    assert "/signup/approve?id=abc123" in html
    assert "/signup/reject?id=abc123" in html


def test_render_escapes_hostile_input():
    html = render_signup_admin_email(_notification(name="<script>alert(1)</script>", note="<img src=x onerror=y>"))
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html


def test_render_handles_missing_note():
    html = render_signup_admin_email(_notification(note=""))
    assert "(none)" in html


def test_send_signup_admin_email_invokes_ses():
    notification = _notification()
    with patch("boto3.client") as client_factory:
        ses_client = MagicMock()
        client_factory.return_value = ses_client
        send_signup_admin_email("admin@example.com", notification)

    client_factory.assert_called_once()
    assert client_factory.call_args.args[0] == "ses"
    ses_client.send_email.assert_called_once()
    _, kwargs = ses_client.send_email.call_args
    assert kwargs["Destination"]["ToAddresses"] == ["admin@example.com"]
    assert "Jane Doe" in kwargs["Message"]["Subject"]["Data"]
    assert "/signup/approve" in kwargs["Message"]["Body"]["Html"]["Data"]


# ---------------------------------------------------------------------------
# SES failure modes (#5375) -- send_signup_admin_email must never swallow a
# delivery failure; it propagates so the route can surface a 5xx rather than
# silently dropping the admin notification.
# ---------------------------------------------------------------------------


def _rejected_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "Email address is not verified"}},
        "SendEmail",
    )


def _throttling_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "Throttling", "Message": "Maximum sending rate exceeded"}},
        "SendEmail",
    )


def _config_error() -> ParamValidationError:
    return ParamValidationError(report="Invalid type for parameter Source")


@pytest.mark.parametrize(
    "make_error",
    [_rejected_error, _throttling_error, _config_error],
    ids=["message-rejected", "throttling", "generic-config"],
)
def test_send_signup_admin_email_propagates_ses_failures(make_error):
    """SES failures (rejection, throttling, and generic/config errors) must
    propagate unmodified -- the caller (backend.routes.signup) relies on this
    to turn the failure into a 502 rather than reporting a false success."""

    notification = _notification()
    with patch("boto3.client") as client_factory:
        ses_client = MagicMock()
        ses_client.send_email.side_effect = make_error()
        client_factory.return_value = ses_client

        with pytest.raises(type(make_error())):
            send_signup_admin_email("admin@example.com", notification)

    ses_client.send_email.assert_called_once()
