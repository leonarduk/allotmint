"""Fixtures for the fund upkeep bot tests (#10482)."""

from __future__ import annotations

import pytest

from backend.common import instruments
from backend.fund_upkeep import charges_agent
from tests.backend.fund_upkeep.fixtures import make_catalogue


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    """Hostnames resolve to a public documentation address; tests never touch real DNS."""
    monkeypatch.setattr(charges_agent, "_resolve_host", lambda _host: ["93.184.216.34"])


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    yield make_catalogue(tmp_path, monkeypatch)
    instruments.get_instrument_meta.cache_clear()
