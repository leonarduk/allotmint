"""Fixtures for the fund upkeep bot tests (#10482)."""

from __future__ import annotations

import pytest

from backend.common import instruments
from tests.backend.fund_upkeep.fixtures import make_catalogue


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    yield make_catalogue(tmp_path, monkeypatch)
    instruments.get_instrument_meta.cache_clear()
