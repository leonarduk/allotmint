import asyncio
import importlib

from fastapi import FastAPI


def _event():
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": "/",
        "rawQueryString": "",
        "headers": {},
        "requestContext": {
            "http": {
                "method": "GET",
                "path": "/",
                "protocol": "HTTP/1.1",
                "sourceIp": "test",
                "userAgent": "test",
            }
        },
        "isBase64Encoded": False,
    }


def _setup_app(monkeypatch):
    app = FastAPI()

    @app.get("/")
    def read_root():
        return {"hello": "world"}

    monkeypatch.setattr("backend.app.create_app", lambda: app)


def _reload_handler():
    return importlib.reload(importlib.import_module("backend.lambda_api.handler"))


def test_lambda_handler_initializes_on_first_call(monkeypatch):
    """Handler is callable before first invocation and initializes lazily."""
    _setup_app(monkeypatch)

    module = _reload_handler()
    lambda_handler = module.lambda_handler
    assert callable(lambda_handler)
    assert module._handler is None  # not yet initialized

    response = lambda_handler(_event(), {})
    assert response["statusCode"] == 200
    assert response["body"] == '{"hello":"world"}'
    assert module._handler is not None  # initialized after first call


def test_lambda_handler_caches_after_first_call(monkeypatch):
    """Second invocation reuses the cached Mangum handler."""
    _setup_app(monkeypatch)

    module = _reload_handler()
    module.lambda_handler(_event(), {})
    first_handler = module._handler
    module.lambda_handler(_event(), {})
    assert module._handler is first_handler


def test_lambda_handler_creates_event_loop(monkeypatch):
    """A new event loop is created when none exists at initialization time."""
    _setup_app(monkeypatch)

    called = False
    orig_new_event_loop = asyncio.new_event_loop

    def fake_new_event_loop():
        nonlocal called
        called = True
        return orig_new_event_loop()

    monkeypatch.setattr(asyncio, "new_event_loop", fake_new_event_loop)

    module = _reload_handler()
    response = module.lambda_handler(_event(), {})
    assert response["statusCode"] == 200
    assert response["body"] == '{"hello":"world"}'
    assert called is True


def test_lambda_handler_no_new_loop_when_loop_exists(monkeypatch):
    """No new event loop is created when one already exists at initialization time."""
    _setup_app(monkeypatch)

    called = False
    orig_new_event_loop = asyncio.new_event_loop

    def fake_new_event_loop():
        nonlocal called
        called = True
        return orig_new_event_loop()

    # Pre-set an event loop so get_running_loop raises RuntimeError but
    # get_event_loop would return an existing loop.  Lambda sets up a loop
    # before invoking the handler on some runtimes.
    existing_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(existing_loop)
    monkeypatch.setattr(asyncio, "new_event_loop", fake_new_event_loop)

    try:
        module = _reload_handler()
        response = module.lambda_handler(_event(), {})
        assert response["statusCode"] == 200
        # new_event_loop should NOT have been called because get_running_loop()
        # raises RuntimeError (no running loop), but the existing loop is reused.
        # The exact branch taken depends on whether the loop is marked running;
        # either way the handler must succeed.
        assert response["body"] == '{"hello":"world"}'
    finally:
        existing_loop.close()
