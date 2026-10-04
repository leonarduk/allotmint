"""Scaling-override lookup gaps left after #7787's data fixes.

The table values for ADM/AV/CLIG/HICL are pinned by
``tests/test_scaling_overrides_table.py``. These tests cover two lookup
behaviours that the data fix alone does not:

- the configured ``DATA_ROOT`` table (the live dataset, e.g.
  ``../allotmint-data/scaling_overrides.json``) must win over the repo's
  fallback copy, which previously shadowed it whenever ``repo_root`` was set;
- a caller that passes no exchange (``routes/timeseries_meta`` passes ``""``)
  must still pick up an ``"L"`` override for ``"AV"`` / ``"AV."``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.common import instruments
from backend.common import portfolio_utils as pu
from backend.utils import timeseries_helpers as th


@pytest.fixture
def gbp_metadata(monkeypatch):
    """Metadata says GBP, so only the override table can supply a pence factor."""
    monkeypatch.setattr(instruments, "get_instrument_meta", lambda ticker: {"currency": "GBP"})
    monkeypatch.setattr(pu, "get_security_meta", lambda ticker: {"currency": "GBP"})


def _write_overrides(directory: Path, table: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "scaling_overrides.json").write_text(json.dumps(table))


def test_data_root_table_wins_over_repo_copy(monkeypatch, tmp_path, gbp_metadata):
    data_root = tmp_path / "allotmint-data"
    repo_root = tmp_path / "repo"
    _write_overrides(data_root, {"L": {"BP": 0.01}})
    _write_overrides(repo_root / "data", {"L": {"GSK": 0.01}})
    monkeypatch.setattr(th.config, "data_root", data_root)
    monkeypatch.setattr(th.config, "repo_root", repo_root)

    assert th._scaling_overrides_path() == data_root / "scaling_overrides.json"
    assert th.get_scaling_override("BP.L", "L", None) == pytest.approx(0.01)


def test_repo_copy_used_when_data_root_has_no_table(monkeypatch, tmp_path, gbp_metadata):
    repo_root = tmp_path / "repo"
    _write_overrides(repo_root / "data", {"L": {"BP": 0.01}})
    monkeypatch.setattr(th.config, "data_root", tmp_path / "empty-data-root")
    monkeypatch.setattr(th.config, "repo_root", repo_root)

    assert th._scaling_overrides_path() == repo_root / "data" / "scaling_overrides.json"
    assert th.get_scaling_override("BP.L", "L", None) == pytest.approx(0.01)


@pytest.mark.parametrize("ticker", ["AV", "AV.", "AV.L"])
def test_l_override_applies_without_explicit_exchange(monkeypatch, tmp_path, gbp_metadata, ticker):
    _write_overrides(tmp_path, {"L": {"AV": 0.01}})
    monkeypatch.setattr(th.config, "data_root", tmp_path)

    assert th.get_scaling_override(ticker, "", None) == pytest.approx(0.01)


def test_inferred_exchange_prefers_suffix_and_rejects_ambiguity():
    table = {"L": {"ABC": 0.01}, "N": {"ABC": 1}, "*": {"AV": 2}}
    assert th._infer_override_exchange("XYZ.N", "XYZ", table) == "N"
    assert th._infer_override_exchange("ABC", "ABC", table) == ""
    assert th._infer_override_exchange("AV.", "AV", table) == ""
    assert th._infer_override_exchange("AV.", "AV", {"L": {"AV": 0.01}}) == "L"
