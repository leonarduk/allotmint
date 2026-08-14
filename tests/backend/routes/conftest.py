"""Shared fixtures for tests under tests/backend/routes/."""

from __future__ import annotations

import pytest


@pytest.fixture
def reset_warning_flag(monkeypatch: pytest.MonkeyPatch):
    """Reset a module-level "warn once per process" flag before a test runs.

    Some modules (e.g. ``backend.routes.transactions``) use a ``_warned_*``
    module-level boolean to emit a given warning only once per process. Tests
    that need to observe the warning must reset the flag first, since an
    earlier test running in the same process may already have flipped it to
    True -- otherwise the warning silently never fires and the assertion
    becomes a false pass. This consolidates the previously-repeated inline
    ``monkeypatch.setattr(module, "_warned_x", False)`` calls (issue #5343).

    Usage:
        def test_something(reset_warning_flag):
            reset_warning_flag(transactions_module, "_warned_missing_data_bucket")
    """

    def _reset(module: object, attr_name: str) -> None:
        monkeypatch.setattr(module, attr_name, False)

    return _reset
