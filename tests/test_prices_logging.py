import importlib
import logging
import sys

import pytest

import backend.common
import backend.common.prices  # noqa: F401  # ensure the original module is loaded so it can be restored


def test_prices_import_does_not_configure_root_logger():
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.WARNING)

    # Force a fresh import, but restore the original module object in sys.modules
    # and on the ``backend.common`` package afterwards. A bare ``sys.modules.pop``
    # leaks the re-imported module into later tests, leaving any test that did
    # ``import backend.common.prices as prices`` patching a stale module that
    # ``backend.lambda_api.price_refresh`` no longer sees.
    original = sys.modules["backend.common.prices"]
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.delitem(sys.modules, "backend.common.prices")
            # The re-import rebinds the package attribute, so record the original
            # *before* importing; leaving the context restores it.
            mp.setattr(backend.common, "prices", original)
            fresh = importlib.import_module("backend.common.prices")
            assert fresh is not original
            assert root_logger.level == logging.WARNING
    finally:
        root_logger.setLevel(original_level)

    assert sys.modules["backend.common.prices"] is original
    assert backend.common.prices is original
