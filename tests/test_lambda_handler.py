import asyncio
import importlib

from fastapi import FastAPI
from mangum import Mangum


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


def test_lambda_handler_creates_event_loop(monkeypatch):
    _setup_app(monkeypatch)

    called = False
    orig_new_event_loop = asyncio.new_event_loop

    def fake_new_event_loop():
        nonlocal called
        called = True
        return orig_new_event_loop()

    monkeypatch.setattr(asyncio, "new_event_loop", fake_new_event_loop)

    module = _reload_handler()

    lambda_handler = module.lambda_handler
    assert isinstance(lambda_handler, Mangum)

    response = lambda_handler(_event(), {})
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "application/json"
    assert response["body"] == "{\"hello\":\"world\"}"
    assert response["isBase64Encoded"] is False
    assert called is True


def test_lambda_handler_with_running_loop(monkeypatch):
    _setup_app(monkeypatch)

    called = False
    orig_new_event_loop = asyncio.new_event_loop

    def fake_new_event_loop():
        nonlocal called
        called = True
        return orig_new_event_loop()

    monkeypatch.setattr(asyncio, "new_event_loop", fake_new_event_loop)

    async def load_handler():
        module = _reload_handler()
        return module.lambda_handler

    lambda_handler = asyncio.run(load_handler())
    assert isinstance(lambda_handler, Mangum)
    assert called is False
