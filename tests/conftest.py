import asyncio
import copy
import importlib.util
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

from backend import app as app_module
from backend import auth as auth_module
from backend.config import config

_real_verify_google_token = auth_module.verify_google_token

# The private cicaid automation dependency (requirements-automation.txt) is
# only installed when CI has CICAID_PRO_TOKEN, and without it these modules
# fail at import. ci.yml passes --ignore for them in that case; mirror it
# here so a plain `pytest tests/` (fork PRs, local runs, automated
# verifiers) collects the rest of the suite instead of erroring.
if importlib.util.find_spec("cicaid_devtools") is None:
    collect_ignore = [
        "test_review_common.py",
        "test_ai_review_scripts.py",
        "scripts/test_n_review_issue.py",
    ]


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """Lightweight async test support when ``pytest-asyncio`` isn't available."""

    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    call_kwargs = {
        name: value for name, value in pyfuncitem.funcargs.items() if name in pyfuncitem._fixtureinfo.argnames
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
def isolate_timeseries_cache(tmp_path_factory):
    """Redirect the default timeseries cache to a session-scoped temp dir.

    ``backend.timeseries.cache._CACHE_BASE`` is bound once at import time
    from ``TIMESERIES_CACHE_BASE`` / ``config.timeseries_cache_base`` -
    ``data/timeseries`` under the repo's own config.yaml - so any test that
    fetches prices without redirecting the cache wrote parquet files into
    the real data/timeseries directory. That tree is gitignored, so the
    files piled up across runs in a long-lived checkout (local dev, or an
    automated verifier's workspace) and later tests could read them.
    Tests that want particular cached data still point ``_CACHE_BASE`` at
    their own directory; this only changes the default. Not restored at
    teardown, for the same straggler-thread reason as isolate_prices_json.
    """
    from backend.timeseries import cache as ts_cache

    tmp_cache = tmp_path_factory.mktemp("timeseries")
    ts_cache._CACHE_BASE = str(tmp_cache)
    config.timeseries_cache_base = str(tmp_cache)
    yield tmp_cache


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
def isolate_price_triggers(tmp_path, monkeypatch):
    """Keep price-trigger storage off ``data/`` and off any faked S3 bucket."""
    monkeypatch.setenv("PRICE_TRIGGERS_URI", f"file://{tmp_path / 'price_triggers.json'}")


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


@pytest.fixture(autouse=True)
def clear_instrument_meta_cache():
    """Reset the process-wide instrument metadata caches between tests.

    ``instruments.get_instrument_meta`` (and ``_persisted_metadata_exchanges``)
    are ``lru_cache``d. Several tests point the instruments directory
    elsewhere or stub the metadata sources and then look a real ticker up;
    not all clear the cache afterwards, so a later test in the same process
    could get that stubbed entry - e.g. HFEL.L without a sector. Under
    pytest-xdist which test ran first differs per worker, so this showed up
    as a flaky test_get_security_meta_includes_sector_and_region.
    """
    from backend.common import instrument_classification, instruments

    def _clear():
        for name in ("get_instrument_meta", "_persisted_metadata_exchanges"):
            clear = getattr(getattr(instruments, name, None), "cache_clear", None)
            if clear is not None:
                clear()
        # Classification overrides are cached per file mtime (#9196).
        instrument_classification.clear_overrides_cache()

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def clear_opportunities_cache():
    """Reset the module-level /opportunities response cache between tests.

    backend/routes/opportunities.py caches responses in a process-wide dict
    keyed by (group|tickers, days, limit, min_weight) to avoid recomputing
    trading signals on every request. Without this reset, two tests that
    happen to request the same params (e.g. group="growth", days=1, limit=5)
    but stub different mock data would leak a cached response from whichever
    test ran first.
    """
    from backend.routes import opportunities as opportunities_module

    opportunities_module._OPPORTUNITIES_CACHE.clear()
    yield
    opportunities_module._OPPORTUNITIES_CACHE.clear()


@pytest.fixture(autouse=True)
def clear_group_portfolio_cache():
    """Reset the process-wide group-portfolio cache between tests.

    ``backend/common/portfolio_cache.py`` caches built group portfolios for 60s
    so that one page load does not re-run a multi-second build once per
    endpoint. Without this reset, a test that stubs ``build_group_portfolio``
    with one fixture is answered from whatever an earlier test cached under the
    same (slug, as_of, demo scope) key -- the stub looks ignored.
    """
    from backend.common import portfolio_cache

    portfolio_cache.invalidate_group_portfolios()
    yield
    portfolio_cache.invalidate_group_portfolios()


@pytest.fixture(autouse=True)
def reset_stooq_unreachable_cooldown(monkeypatch):
    """Clear the Stooq unreachable cooldown and per-ticker skips for each test.

    A test that simulates a Stooq timeout puts Stooq into a process-wide
    cooldown (#7877) or skips that ticker (#7913); without this reset, later
    tests that stub a successful Stooq response would be skipped. monkeypatch
    restores the pre-test values on teardown, undoing any state the test left.
    """
    from backend.timeseries import fetch_stooq_timeseries

    monkeypatch.setattr(fetch_stooq_timeseries, "_STOOQ_UNREACHABLE_UNTIL", 0.0)
    monkeypatch.setattr(fetch_stooq_timeseries, "_STOOQ_CONSECUTIVE_READ_TIMEOUTS", 0)
    monkeypatch.setattr(fetch_stooq_timeseries, "_STOOQ_TICKER_SKIP_UNTIL", {})


@pytest.fixture(autouse=True)
def restore_timeseries_cache_module():
    """Put the original ``backend.timeseries.cache`` back after each test.

    Some tests pop the module from ``sys.modules`` and re-import it to get
    fresh module state. Without this, the fresh copy leaks into later tests:
    they patch it via ``importlib.import_module`` while modules that did
    ``from backend.timeseries.cache import ...`` at import time
    (``holding_utils``, ``portfolio_utils``, ``group_portfolio``, ...) still
    call the original. A later test's result then depends on whether a
    reload test ran before it (#7990).
    """
    import sys

    from backend import timeseries

    original = sys.modules.get("backend.timeseries.cache")
    yield
    if original is not None and sys.modules.get("backend.timeseries.cache") is not original:
        sys.modules["backend.timeseries.cache"] = original
        timeseries.cache = original


@pytest.fixture(autouse=True)
def isolate_timeseries_refresh_queue(monkeypatch):
    """Keep the background price-refresh worker (#7917) from starting in tests.

    A test that reads in cache-only mode with offline mode off queues its stale
    tickers; a worker thread started then could outlive the test's fetcher
    monkeypatches and reach a real price source. Tests call ``drain()``
    themselves when they want the refresh to run.
    """
    from backend.timeseries import cache, refresh_queue

    monkeypatch.setattr(refresh_queue, "autostart", False)
    refresh_queue.reset()
    cache._FX_FRAMES.clear()
    yield
    refresh_queue.reset()
    cache._FX_FRAMES.clear()


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


# --- Shared ``config`` object: put it back after every test --------------------
#
# Many tests assign to ``config`` attributes directly (``config.app_env =
# "aws"``, ``config.accounts_root = ...``) and not all of them undo it. In
# serial order a later test usually happened to reset what it needed; with
# pytest-xdist each worker runs a different order, and a leaked ``app_env =
# "aws"`` or ``accounts_root`` made unrelated tests fail.
#
# The baseline is taken once, after the session fixtures that deliberately set
# ``config`` up (offline mode, the isolated prices and timeseries paths), and
# restored in pytest_runtest_teardown *after* every function fixture has torn
# down. A restore inside an autouse fixture ran before monkeypatch's own undo
# (fixture teardown order), and that undo re-sets values through
# ``Config.__setattr__`` - which e.g. marks ``allowed_emails`` as overridden
# and made test_config.py's reload_config() keep a stale list.
_CONFIG_BASELINE: dict | None = None


@pytest.fixture(scope="session", autouse=True)
def shared_config_baseline(enable_offline_mode, isolate_prices_json, isolate_timeseries_cache):
    global _CONFIG_BASELINE
    _CONFIG_BASELINE = copy.deepcopy(vars(config))
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    yield
    if _CONFIG_BASELINE is not None:
        state = vars(config)
        state.clear()
        state.update(copy.deepcopy(_CONFIG_BASELINE))
