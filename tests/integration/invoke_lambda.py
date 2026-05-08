"""Local Lambda invocation helpers for Makefile integration checks."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

FIXED_TIMESTAMP = "2026-05-08T00:00:00Z"


def _noop() -> None:
    pass


def _load_event(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _eventbridge_response(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "body": json.dumps(result, sort_keys=True, separators=(",", ":")),
        "isBase64Encoded": False,
    }


def _invoke_api_http(event: dict[str, Any]) -> dict[str, Any]:
    os.environ.setdefault("APP_ENV", "local")
    os.environ.setdefault("DISABLE_AUTH", "true")
    module = importlib.import_module("backend.lambda_api.handler")
    return module.lambda_handler(event, {})


def _invoke_price_refresh(event: dict[str, Any]) -> dict[str, Any]:
    # Patch backend.common.prices before evicting + re-importing the handler so
    # that the handler's `from backend.common.prices import refresh_prices` picks
    # up the stub on re-import (the prices module stays cached in sys.modules).
    import backend.common.prices as prices

    def refresh_prices_stub() -> dict[str, Any]:
        return {
            "tickers": [],
            "snapshot": {},
            "timestamp": FIXED_TIMESTAMP,
        }

    prices.refresh_prices = refresh_prices_stub
    os.environ["ALLOTMINT_ENABLE_TRADING_AGENT"] = "false"
    sys.modules.pop("backend.lambda_api.price_refresh", None)
    module = importlib.import_module("backend.lambda_api.price_refresh")
    module.trading_agent = SimpleNamespace(run=_noop)
    return _eventbridge_response(module.lambda_handler(event, {}))


def _invoke_trading_agent(event: dict[str, Any]) -> dict[str, Any]:
    # Patch backend.agent.trading_agent before evicting + re-importing the handler
    # so the handler's `from backend.agent.trading_agent import run` picks up the stub.
    import backend.agent.trading_agent as trading_agent

    trading_agent.run = _noop
    sys.modules.pop("backend.lambda_api.trading_agent", None)
    module = importlib.import_module("backend.lambda_api.trading_agent")
    return _eventbridge_response(module.lambda_handler(event, {}))


def _handler(invocation_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    handlers = {
        "api-http": _invoke_api_http,
        "price-refresh": _invoke_price_refresh,
        "trading-agent": _invoke_trading_agent,
    }
    try:
        return handlers[invocation_name]
    except KeyError as exc:
        known = ", ".join(sorted(handlers))
        raise SystemExit(f"Unknown invocation '{invocation_name}'. Expected one of: {known}") from exc


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m tests.integration.invoke_lambda <name> <event.json>")

    event = _load_event(sys.argv[2])
    response = _handler(sys.argv[1])(event)
    json.dump(response, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
