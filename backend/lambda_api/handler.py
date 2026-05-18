"""
AWS Lambda entry-point (Python 3.12 runtime or container).
Handler: backend.lambda_api.handler.lambda_handler

Initialization is deferred to the first invocation rather than the Lambda
INIT phase.  The INIT phase has a hard 10-second limit enforced by AWS; the
full application startup (FastAPI app creation, router registration, snapshot
warmup) can exceed that limit on a cold start.  Deferring to the first
invocation moves this work into normal invocation time, which has a
configurable and far more generous timeout.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

_handler = None


def _create_handler():
    from mangum import Mangum

    from backend.app import create_app

    try:  # pragma: no cover - the exception path is platform specific
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    return Mangum(create_app())


def lambda_handler(event, context):
    """AWS Lambda handler with lazy application initialization.

    The underlying Mangum/FastAPI handler is created on the first invocation
    and cached for all subsequent calls in the same Lambda execution context.
    """
    global _handler
    if _handler is None:
        logger.info("Lambda cold start: initializing application on first invocation")
        _handler = _create_handler()
    return _handler(event, context)
