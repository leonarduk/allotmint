"""Resolve paths to application sources shared by the CDK stacks."""

import os
from pathlib import Path
from typing import Protocol


class _ContextNode(Protocol):
    """The subset of a CDK construct node needed by the path resolver."""

    def try_get_context(self, key: str) -> object | None: ...


def resolve_app_root(node: _ContextNode | None = None) -> Path:
    """Return the checkout containing the backend and frontend application."""
    context_root = node.try_get_context("appRoot") if node is not None else None
    configured_root = context_root or os.getenv("ALLOTMINT_APP_ROOT")
    if configured_root is None:
        return Path(__file__).resolve().parents[2]

    app_root = Path(str(configured_root)).expanduser().resolve()
    missing = [name for name in ("backend", "frontend") if not (app_root / name).is_dir()]
    if missing:
        raise ValueError(
            f"Configured AllotMint app root {app_root} is missing required directories: "
            f"{', '.join(missing)}. Set ALLOTMINT_APP_ROOT or CDK context appRoot "
            "to the application checkout."
        )
    return app_root
