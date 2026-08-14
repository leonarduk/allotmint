from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, ParamValidationError

from backend.emails.signup_approved import (
    render_signup_approved_email,
    send_signup_approved_email,
)


def test_render_includes_greeting_and_login_link():
    html = render_signup_approved_email("Jane Doe", "https://allotmint.example/login")
    assert "Jane Doe" in html
    assert "https://allotmint.example/login" in html
    assert "<a href=" in html


def test_render_escapes_hostile_name():
    html = render_signup_approved_email("<script>alert(1)</script>", "https://allotmint.example/login")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_handles_missing_login_url():
    html = render_signup_approved_email("Jane", "")
    assert "You can now log in to AllotMint." in html


def test_send_signup_approved_email_invokes_ses():
    with patch("boto3.client") as client_factory:
        ses_client = MagicMock()
        client_factory.return_value = ses_client
        send_signup_approved_email("jane@example.com", "Jane Doe", "https://allotmint.example/login")

    client_factory.assert_called_once()
    assert client_factory.call_args.args[0] == "ses"
    ses_client.send_email.assert_called_once()
    _, kwargs = ses_client.send_email.call_args
    assert kwargs["Destination"]["ToAddresses"] == ["jane@example.com"]
    assert "login is ready" in kwargs["Message"]["Subject"]["Data"]


# ---------------------------------------------------------------------------
# SES failure modes (#5375) -- send_signup_approved_email must never swallow a
# delivery failure; it propagates so the route can surface a 5xx rather than
# reporting a false "approved and notified" success to the caller.
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
def test_send_signup_approved_email_propagates_ses_failures(make_error):
    """SES failures (rejection, throttling, and generic/config errors) must
    propagate unmodified -- the caller (backend.routes.signup) relies on this
    to turn the failure into a 502 rather than reporting a false success even
    though the user was already provisioned by this point."""

    with patch("boto3.client") as client_factory:
        ses_client = MagicMock()
        ses_client.send_email.side_effect = make_error()
        client_factory.return_value = ses_client

        with pytest.raises(type(make_error())):
            send_signup_approved_email("jane@example.com", "Jane Doe", "https://allotmint.example/login")

    ses_client.send_email.assert_called_once()
