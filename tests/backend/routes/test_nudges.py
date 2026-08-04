import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routes import nudges


def _fake_request(accounts_root: Path) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(accounts_root=accounts_root)))


def test_validate_owner_logs_and_raises_404_when_unknown_and_disallowed(monkeypatch, caplog, tmp_path):
    """``_validate_owner(allow_unknown=False)`` must call ``log_owner_not_found``
    and raise a 404 when the owner isn't among the discovered plots (#5717).
    Every route in this module currently calls ``_validate_owner`` with
    ``allow_unknown=True``, so this branch is otherwise dead from the router's
    perspective and needs direct coverage."""
    monkeypatch.setattr(nudges.data_loader, "list_plots", lambda root: [])

    with caplog.at_level(logging.WARNING, logger="backend.common.errors"):
        with pytest.raises(HTTPException) as excinfo:
            nudges._validate_owner("ghost", _fake_request(tmp_path), allow_unknown=False)

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == nudges.OWNER_NOT_FOUND
    assert "owner lookup: no owner found for owner=ghost" in caplog.text
    assert "total_plots_discovered=0" in caplog.text


def test_validate_owner_does_not_raise_when_unknown_and_allowed(monkeypatch, caplog, tmp_path):
    """The live routes pass ``allow_unknown=True``, so an unknown owner must
    pass through silently -- no log, no exception."""
    monkeypatch.setattr(nudges.data_loader, "list_plots", lambda root: [])

    with caplog.at_level(logging.WARNING, logger="backend.common.errors"):
        nudges._validate_owner("ghost", _fake_request(tmp_path), allow_unknown=True)

    assert caplog.text == ""
