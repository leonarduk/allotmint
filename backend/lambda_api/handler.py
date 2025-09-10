"""
AWS Lambda entry-point (Python 3.12 runtime or container).
Handler: backend.lambda_api.handler.lambda_handler
"""

import asyncio

from mangum import Mangum

from backend.app import create_app


def _create_handler() -> Mangum:
    """Create the Mangum handler ensuring an event loop exists.

    Mangum expects an event loop to be available. On some platforms
    (e.g. Windows) ``asyncio.get_event_loop()`` may raise a ``RuntimeError``
    when no loop has been set. The tests run in such an environment so we
    create and set a new loop if needed before instantiating ``Mangum``.
    """

    try:  # pragma: no cover - the exception path is platform specific
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    return Mangum(create_app())


lambda_handler = _create_handler()
