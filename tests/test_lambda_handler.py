import importlib

from fastapi import FastAPI
from mangum import Mangum


def test_lambda_handler(monkeypatch):
    app = FastAPI()

    @app.get("/")
    def read_root():
        return {"hello": "world"}

    def mock_create_app():
        return app

    monkeypatch.setattr("backend.app.create_app", mock_create_app)

    module = importlib.reload(importlib.import_module("backend.lambda_api.handler"))

    lambda_handler = module.lambda_handler
    assert isinstance(lambda_handler, Mangum)
    assert callable(lambda_handler)

    event = {
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

    response = lambda_handler(event, {})
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "application/json"
    assert response["body"] == "{\"hello\":\"world\"}"
    assert response["isBase64Encoded"] is False
