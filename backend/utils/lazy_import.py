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
    so ``unittest.mock.patch`` and pytest ``monkeypatch`` work transparently.

    ``__getattribute__`` is overridden (rather than just ``__getattr__``) so
    that ``proxy.__dict__`` returns the *real module's* ``__dict__``.  This
    matters for ``unittest.mock.patch`` teardown: mock inspects
    ``target.__dict__[attr]`` to decide whether to restore via ``setattr``
    (``is_local=True``) or ``delattr`` (``is_local=False``).  Without this,
    the proxy's own empty ``__dict__`` makes mock think the attribute is
    inherited and calls ``delattr(proxy, attr)``, which raises
    ``AttributeError`` because the proxy has no ``attr`` in its own dict.
    Exposing the real module's ``__dict__`` gives mock the correct view so it
    always restores via ``setattr``.
    """

    # Sentinel attributes that must resolve on the proxy itself, not the target.
    _SELF_ATTRS = frozenset({"_lazy_name", "_load", "__class__", "__repr__"})

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "_lazy_name", name)

    def _load(self) -> Any:
        name = object.__getattribute__(self, "_lazy_name")
        module = sys.modules.get(name)
        if module is None:
            module = importlib.import_module(name)
        return module

    def __getattribute__(self, attr: str) -> Any:
        if attr in _LazyModule._SELF_ATTRS:
            return object.__getattribute__(self, attr)
        if attr == "__dict__":
            # Expose the real module's __dict__ so mock.patch is_local detection
            # correctly identifies module attributes as local and uses setattr
            # (not delattr) during teardown.
            return object.__getattribute__(self, "_load")().__dict__
        return getattr(object.__getattribute__(self, "_load")(), attr)

    def __setattr__(self, attr: str, value: Any) -> None:
        if attr == "_lazy_name":
            object.__setattr__(self, attr, value)
        else:
            setattr(object.__getattribute__(self, "_load")(), attr, value)

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
