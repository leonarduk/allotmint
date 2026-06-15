from unittest.mock import MagicMock, patch

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
    html = render_signup_admin_email(
        _notification(name="<script>alert(1)</script>", note="<img src=x onerror=y>")
    )
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
