import pytest
from fastapi import HTTPException

from backend import auth


@pytest.mark.parametrize(
    "client_id, verify_response, allowed_emails, expected",
    [
        # Missing Google client ID -> 400
        (None, {"email": "a@b.com", "email_verified": True}, {"a@b.com"}, 400),
        # id_token.verify_oauth2_token raises -> 401
        ("client", Exception("boom"), {"a@b.com"}, 401),
        # Token payload lacks email_verified -> 401
        ("client", {"email": "a@b.com"}, {"a@b.com"}, 401),
        # Token payload lacks email -> 401
        ("client", {"email_verified": True}, {"a@b.com"}, 401),
        # _allowed_emails returns empty set -> 403
        ("client", {"email": "a@b.com", "email_verified": True}, set(), 403),
        # _allowed_emails excludes email -> 403
        ("client", {"email": "a@b.com", "email_verified": True}, {"c@d.com"}, 403),
        # Successful authentication -> return email
        ("client", {"email": "a@b.com", "email_verified": True}, {"a@b.com"}, "a@b.com"),
    ],
)
def test_verify_google_token(monkeypatch, client_id, verify_response, allowed_emails, expected):
    monkeypatch.setattr(auth.config, "google_client_id", client_id)
    called = False

    def fake_verify(token, request, cid):
        nonlocal called
        called = True
        assert cid == client_id
        if isinstance(verify_response, Exception):
            raise verify_response
        return verify_response

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: allowed_emails)

    if client_id is None:
        with pytest.raises(HTTPException) as exc:
            auth.verify_google_token("token")
        assert exc.value.status_code == expected
        assert called is False
    elif isinstance(expected, int):
        with pytest.raises(HTTPException) as exc:
            auth.verify_google_token("token")
        assert exc.value.status_code == expected
    else:
        assert auth.verify_google_token("token") == expected
