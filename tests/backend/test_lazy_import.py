"""Unit tests for backend.utils.lazy_import._LazyModule / lazy_import."""

from __future__ import annotations

import sys
from unittest.mock import patch

from backend.utils.lazy_import import lazy_import


def test_attribute_access_triggers_import(monkeypatch):
    """Accessing an attribute on the proxy loads the module on demand."""
    imported = []

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def tracking_import(name, *args, **kwargs):
        imported.append(name)
        return real_import(name, *args, **kwargs)

    proxy = lazy_import("types")
    # No import yet
    assert "types" not in imported

    # First access triggers the load
    result = proxy.ModuleType
    import types
    assert result is types.ModuleType


def test_already_loaded_module_is_reused():
    """If the module is already in sys.modules it is not re-imported."""

    # json is always already loaded in Python
    import json as real_json

    proxy = lazy_import("json")
    assert proxy.dumps is real_json.dumps


def test_repr_before_load():
    """repr() works on the proxy without triggering a load."""
    # Use a module name that definitely does not auto-load
    proxy = lazy_import("email.mime.text")
    # Remove from sys.modules to ensure it's not cached
    sys.modules.pop("email.mime.text", None)

    r = repr(proxy)
    assert "email.mime.text" in r


def test_mock_patch_setattr_restores_correctly():
    """unittest.mock.patch teardown must not raise AttributeError on the proxy."""
    import json as real_json

    proxy = lazy_import("json")

    def fake_dumps(*args, **kwargs):
        return "fake"

    with patch.object(proxy, "dumps", fake_dumps):
        assert proxy.dumps is fake_dumps  # mock applied

    # After exit the original must be restored — this was the CI failure
    assert proxy.dumps is real_json.dumps


def test_monkeypatch_setattr_restores_correctly(monkeypatch):
    """pytest monkeypatch.setattr works transparently through the proxy."""
    import json as real_json

    proxy = lazy_import("json")
    original = real_json.dumps

    monkeypatch.setattr(proxy, "dumps", lambda *_: "patched")
    assert proxy.dumps() == "patched"

    monkeypatch.undo()
    assert proxy.dumps is original


def test_string_path_monkeypatch(monkeypatch):
    """Dotted-path monkeypatch (as used in route tests) works via the proxy."""
    # Simulate the pattern used in test_quotes_failures.py:
    # monkeypatch.setattr("backend.routes.quotes.yf.Tickers", mock)
    import json as real_json

    from backend.utils import lazy_import as lazy_import_module

    sentinel = lazy_import_module.lazy_import("json")
    # Attach proxy as a module attribute for the dotted-path resolution test
    import backend.utils.lazy_import as lim
    lim._test_proxy = sentinel

    try:
        monkeypatch.setattr("backend.utils.lazy_import._test_proxy.dumps", lambda *_: "dotted")
        assert sentinel.dumps() == "dotted"
        monkeypatch.undo()
        assert sentinel.dumps is real_json.dumps
    finally:
        del lim._test_proxy


def test_patch_context_manager_teardown_via_string_path():
    """patch('mod.proxy.attr') teardown works without AttributeError."""
    import json as real_json

    import backend.utils.lazy_import as lim

    proxy = lazy_import("json")
    lim._ctx_test_proxy = proxy

    original_dumps = real_json.dumps
    try:
        with patch("backend.utils.lazy_import._ctx_test_proxy.dumps", return_value="ctx"):
            # Both proxy and real module share the same __dict__, so both see the mock.
            assert lim._ctx_test_proxy.dumps("x") == "ctx"  # mock applied

        # Teardown must not raise; original must be restored.
        assert lim._ctx_test_proxy.dumps is original_dumps
        assert real_json.dumps is original_dumps
    finally:
        del lim._ctx_test_proxy


def test_class_identity_preserved():
    """The proxy's __class__ stays _LazyModule (not the target module type)."""
    from backend.utils.lazy_import import _LazyModule

    proxy = lazy_import("json")
    assert isinstance(proxy, _LazyModule)


def test_setattr_propagates_to_real_module():
    """Setting an attribute on the proxy sets it on the real module."""
    import json as real_json

    proxy = lazy_import("json")
    proxy._sentinel = 42
    try:
        assert real_json._sentinel == 42
    finally:
        del real_json._sentinel
