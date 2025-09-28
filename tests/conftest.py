import asyncio
import inspect
import os
from pathlib import Path

try:
    import boto3
except ImportError:  # pragma: no cover - fallback for environments without boto3
    import types

    # Provide a minimal ``boto3`` stub so tests that monkeypatch ``resource`` can
    # still run in environments where the real dependency isn't installed.
    boto3 = types.SimpleNamespace(resource=lambda *args, **kwargs: None)

import pytest

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATA_ROOT", str(Path(__file__).resolve().parent.parent / "data"))

from backend.config import config
from backend import auth as auth_module
from backend import app as app_module

_real_verify_google_token = auth_module.verify_google_token


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """Lightweight async test support when ``pytest-asyncio`` isn't available."""

    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    call_kwargs = {
        name: value
        for name, value in pyfuncitem.funcargs.items()
        if name in pyfuncitem._fixtureinfo.argnames
    }

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test_function(**call_kwargs))
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    return True


@pytest.fixture(scope="session", autouse=True)
def enable_offline_mode():
    """Force backend to run in offline mode for all tests."""
    previous = config.offline_mode
    config.offline_mode = True
    try:
        yield
    finally:
        config.offline_mode = previous


@pytest.fixture(autouse=True)
def mock_google_verify(monkeypatch, request):
    """Stub Google ID token verification for tests.

    Some tests exercise the real Google verification logic by patching the
    low-level :func:`google.oauth2.id_token.verify_oauth2_token` function.
    Those tests live in ``tests/test_google_auth.py`` and expect the
    application's :func:`backend.auth.verify_google_token` helper to run
    unmodified. The original autouse fixture always replaced this helper with a
    stub, causing the Google-auth tests to receive a ``401`` response instead
    of exercising the intended code path. To avoid this interference we skip
    patching for tests defined in that module.
    """

    # ``request`` points at the currently executing test.  When the test file
    # is ``test_google_auth.py`` we leave the real ``verify_google_token`` in
    # place so that those tests can mock the lower level verification function.
    # ``fspath`` is a py.path object representing the test file path.
    fspath = getattr(request, "fspath", None)
    if fspath and fspath.basename == "test_google_auth.py":
        # Ensure the real function is restored even if a previous test patched it
        monkeypatch.setattr(auth_module, "verify_google_token", _real_verify_google_token)
        monkeypatch.setattr(app_module.auth, "verify_google_token", _real_verify_google_token)
        return

    from fastapi import HTTPException

    def fake_verify(token: str):
        if token == "good":
            return "user@example.com"
        if token == "other":
            raise HTTPException(status_code=403, detail="Unauthorized email")
        raise HTTPException(status_code=401, detail="Invalid token")

    monkeypatch.setattr(auth_module, "verify_google_token", fake_verify)
    monkeypatch.setattr(app_module.auth, "verify_google_token", fake_verify)


@pytest.fixture
def quotes_table(monkeypatch):
    """In-memory DynamoDB table for quote tests."""

    items = []

    class FakeTable:
        def put_item(self, Item):
            items.append(Item)

        def scan(self):
            return {"Items": items, "Count": len(items)}

    table = FakeTable()

    class FakeResource:
        def Table(self, _name):
            return table

    original_resource = boto3.resource

    def fake_resource(service_name, *args, **kwargs):
        if service_name == "dynamodb":
            return FakeResource()
        return original_resource(service_name, *args, **kwargs)

    monkeypatch.setattr(boto3, "resource", fake_resource)

    return table
