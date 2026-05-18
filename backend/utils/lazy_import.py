"""Lazy module import proxy to defer heavy library loading to first use.

Route modules are imported at startup (when ``register_routers`` runs) so
that FastAPI can build its route table and OpenAPI schema.  Libraries like
``yfinance`` and ``pandas`` are only needed when those routes are actually
called, not at startup.  Using :func:`lazy_import` instead of a bare
``import`` keeps module-level code fast while leaving test monkeypatching
(``unittest.mock.patch`` / pytest ``monkeypatch.setattr``) fully functional.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any


class _LazyModule:
    """Proxy that loads a module on first attribute access.

    Attribute reads and writes both delegate to the real module once loaded,
    so ``unittest.mock.patch`` and pytest ``monkeypatch`` work transparently:
    patching an attribute on the proxy patches the underlying module.
    """

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "_lazy_name", name)

    def _load(self) -> Any:
        name = object.__getattribute__(self, "_lazy_name")
        module = sys.modules.get(name)
        if module is None:
            module = importlib.import_module(name)
        return module

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._load(), attr)

    def __setattr__(self, attr: str, value: Any) -> None:
        if attr == "_lazy_name":
            object.__setattr__(self, attr, value)
        else:
            setattr(self._load(), attr, value)

    def __repr__(self) -> str:
        name = object.__getattribute__(self, "_lazy_name")
        return f"<LazyModule {name!r}>"


def lazy_import(name: str) -> Any:
    """Return a lazy proxy for the named module.

    The proxy defers the actual ``import`` until the first attribute access,
    keeping Lambda cold-start overhead low for routes that register at module
    load time but call the library only on first request.

    Usage::

        yf = lazy_import("yfinance")   # yfinance not loaded yet
        yf.Tickers("AAPL MSFT")       # loads yfinance on first call
    """
    return _LazyModule(name)
