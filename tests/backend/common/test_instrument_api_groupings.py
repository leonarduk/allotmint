from __future__ import annotations

import pytest

from backend.common import instrument_api as ia


def test_resolve_grouping_uses_catalogue(monkeypatch):
    catalogue = {"shared": {"id": "shared", "name": "Shared Group"}}
    monkeypatch.setattr(ia, "list_group_definitions", lambda: catalogue)

    name, slug = ia._resolve_grouping_details({"grouping_id": "shared"})
    assert name == "Shared Group"
    assert slug == "shared"
    assert ia._derive_grouping({"grouping_id": "shared"}) == "Shared Group"


@pytest.mark.parametrize(
    "meta,expected",
    [
        ({"grouping": "Income"}, ("Income", None)),
        ({"sector": "Technology"}, ("Technology", None)),
        ({"region": "Europe"}, ("Europe", None)),
    ],
)
def test_resolve_grouping_falls_back_to_metadata(monkeypatch, meta, expected):
    monkeypatch.setattr(ia, "list_group_definitions", lambda: {})

    assert ia._resolve_grouping_details(meta) == expected
    assert ia._derive_grouping(meta) == expected[0]
