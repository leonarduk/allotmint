import importlib
import logging
import sys

import backend.common
import backend.common.prices  # noqa: F401  # ensure the original module is loaded so it can be restored


def test_prices_import_does_not_configure_root_logger(monkeypatch):
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.WARNING)

    # Force a fresh import, but via monkeypatch so the original module object is
    # restored in sys.modules and on the ``backend.common`` package at teardown.
    # A bare ``sys.modules.pop`` leaks the re-imported module into later tests,
    # leaving any test that did ``import backend.common.prices as prices`` patching
    # a stale module that ``backend.lambda_api.price_refresh`` no longer sees.
    monkeypatch.delitem(sys.modules, "backend.common.prices")
    monkeypatch.setattr(backend.common, "prices", backend.common.prices)
    try:
        importlib.import_module("backend.common.prices")
        assert root_logger.level == logging.WARNING
    finally:
        root_logger.setLevel(original_level)
