"""Regression test for CVE-2026-54283 (Starlette urlencoded form-data limit bypass).

Starlette >=1.3.1 enforces a 1 MiB per-field size limit when parsing
``application/x-www-form-urlencoded`` bodies via ``Request.form()``. Before the
fix, an oversized field was not rejected cleanly and instead surfaced as an
unhandled server error, allowing memory exhaustion via a single large request.
"""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

OVERSIZED_FIELD_BYTES = 2_000_000
WITHIN_LIMIT_FIELD_BYTES = 100_000


def _build_form_echo_app() -> FastAPI:
    app = FastAPI()

    @app.post("/echo-form")
    async def echo_form(request: Request):
        form = await request.form()
        return {"keys": list(form.keys())}

    return app


def _post_urlencoded_field(client: TestClient, field_size: int):
    payload = "a" * field_size
    return client.post(
        "/echo-form",
        content=f"field={payload}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_oversized_urlencoded_form_is_rejected():
    app = _build_form_echo_app()
    with TestClient(app) as client:
        resp = _post_urlencoded_field(client, OVERSIZED_FIELD_BYTES)
        assert resp.status_code in (400, 413)


def test_within_limit_urlencoded_form_is_accepted():
    app = _build_form_echo_app()
    with TestClient(app) as client:
        resp = _post_urlencoded_field(client, WITHIN_LIMIT_FIELD_BYTES)
        assert resp.status_code == 200
        assert resp.json() == {"keys": ["field"]}
