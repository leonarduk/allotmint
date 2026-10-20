"""
AWS Lambda entry-point (Python 3.12 runtime or container).
Handler: backend.lambda_api.handler.lambda_handler

Initialization is deferred to the first invocation rather than the Lambda
INIT phase.  The INIT phase has a hard 10-second limit enforced by AWS; the
full application startup (FastAPI app creation, router registration, snapshot
warmup) can exceed that limit on a cold start.  Deferring to the first
invocation moves this work into normal invocation time, which has a
configurable and far more generous timeout.

The app's lifespan runs once per execution environment, here, not per
request.  Mangum's default ``lifespan="auto"`` enters and exits the lifespan
around *every* invocation, so each request re-ran the snapshot warmup (two
calls bounded by SNAPSHOT_LOAD_TIMEOUT_SECONDS each) and the shutdown hook
(cancelling background tasks, deleting temp dirs).  Once the warmup started
timing out, every request took ~20s and the UI reported the backend as
unavailable (#11005).
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

_handler = None
# The entered lifespan context, kept referenced so it is not collected.  Its
# shutdown (cancel background tasks, delete temp dirs) is deliberately never
# run: Lambda freezes the environment between requests and discards it whole.
_lifespan = None


def _create_handler():
    global _lifespan
    from mangum import Mangum

    from backend.app import create_app

    # Reuse the thread's event loop if one is set and open, as Mangum does;
    # otherwise create and set one.
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = create_app()
    lifespan = app.router.lifespan_context(app)
    # Mangum serves every request on the thread's current event loop, this
    # one, so background tasks started by the lifespan keep running across
    # invocations.
    loop.run_until_complete(lifespan.__aenter__())
    _lifespan = lifespan
    return Mangum(app, lifespan="off")


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
