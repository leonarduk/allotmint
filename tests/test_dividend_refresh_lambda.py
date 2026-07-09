import importlib
import sys

import backend.common.dividends as dividends


def _import_lambda(monkeypatch, refresh_fn):
    monkeypatch.setattr(dividends, "refresh_dividends", refresh_fn)
    sys.modules.pop("backend.lambda_api.dividend_refresh", None)
    return importlib.import_module("backend.lambda_api.dividend_refresh")


def test_lambda_handler_returns_refresh_result(monkeypatch):
    sentinel = {"dividends_created": 3}
    mod = _import_lambda(monkeypatch, lambda: sentinel)

    result = mod.lambda_handler({}, {})

    assert result is sentinel


def test_lambda_handler_swallows_exception(monkeypatch):
    def _raise():
        raise RuntimeError("provider outage")

    mod = _import_lambda(monkeypatch, _raise)

    result = mod.lambda_handler({}, {})

    assert result["error"] == "provider outage"
    assert result["dividends_created"] == 0
