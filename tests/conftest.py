import asyncio
import inspect
import os
import shutil
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


@pytest.fixture(scope="session", autouse=True)
def isolate_prices_json(tmp_path_factory):
    """Redirect the default price-snapshot path to a session-scoped temp copy.

    ``AppLifecycleService.startup`` (backend/bootstrap/startup.py) fires an
    unconditional background task (``refresh_snapshot_async``) on every app
    startup, which writes through ``portfolio_utils._PRICES_PATH`` — a path
    bound once at import time from ``config.prices_json``. Any test that
    boots the real app via ``TestClient`` therefore risks a background
    refresh racing with the test run and overwriting the committed seed file
    at data/prices/latest_prices.json with live-fetched data (see issue
    #5192). Individual tests that need their own isolated path already
    monkeypatch ``_PRICES_PATH``/``config.prices_json`` per-test; this
    fixture only changes the *default* so nothing falls through to the real
    repo file when a test forgets to.

    Deliberately not restored at teardown: ``refresh_snapshot_async`` hands
    its work to a real OS thread via ``asyncio.to_thread``, and cancelling
    the wrapping asyncio task at app shutdown does not stop a thread already
    in flight. If this fixture restored the original (real) path on
    teardown, a straggler thread from an early test could still finish after
    that restore and write live data into the committed seed file at the
    very end of the run. Leaving the redirect in place for the rest of the
    process lifetime closes that window; nothing after the test session
    needs the original value back.
    """
    from backend.common import portfolio_utils

    real_path = Path(config.prices_json) if config.prices_json else None
    tmp_prices_json = tmp_path_factory.mktemp("prices") / "latest_prices.json"
    if real_path and real_path.exists():
        shutil.copy(real_path, tmp_prices_json)

    config.prices_json = tmp_prices_json
    portfolio_utils._PRICES_PATH = tmp_prices_json
    yield tmp_prices_json


@pytest.fixture(autouse=True)
def mock_google_verify(monkeypatch, request):
    """Stub Google ID token verification for tests.

    Some tests exercise the real Google verification logic by patching the
    low-level :func:`google.oauth2.id_token.verify_oauth2_token` function.
    Those tests live in ``tests/test_google_auth.py``, ``tests/backend/test_auth.py``,
    and ``tests/backend/test_auth_module.py``. They expect the application's
    :func:`backend.auth.verify_google_token` helper to run unmodified.
    To avoid this interference we skip patching for tests defined in those modules.
    """

    # ``request`` points at the currently executing test.  When the test file
    # is one of the auth test modules, we leave the real ``verify_google_token`` in
    # place so that those tests can mock the lower level verification function.
    # ``fspath`` is a py.path object representing the test file path.
    fspath = getattr(request, "fspath", None)
    if fspath and fspath.basename in ("test_google_auth.py", "test_auth.py", "test_auth_module.py"):
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
