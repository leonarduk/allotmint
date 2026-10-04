"""Scaling-override lookup gaps left after #7787's data fixes.

The table values for ADM/AV/CLIG/HICL are pinned by
``tests/test_scaling_overrides_table.py``. These tests cover two lookup
behaviours that the data fix alone does not:

- the configured ``DATA_ROOT`` table (the live dataset, e.g.
  ``../allotmint-data/scaling_overrides.json``) is overlaid on the repo's
  table: DATA_ROOT wins per symbol, repo-only symbols (e.g. ``SGLN``) are kept.
  Previously the repo copy replaced the DATA_ROOT table whenever
  ``repo_root`` was set;
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


BUNDLED = Path(th.__file__).resolve().parents[2] / "data" / "scaling_overrides.json"


def _point_at(monkeypatch, tmp_path, data_table=None, repo_table=None):
    """Configure data_root / repo_root, writing only the tables given."""
    data_root = tmp_path / "allotmint-data"
    repo_root = tmp_path / "repo"
    if data_table is not None:
        _write_overrides(data_root, data_table)
    if repo_table is not None:
        _write_overrides(repo_root / "data", repo_table)
    monkeypatch.setattr(th.config, "data_root", data_root)
    monkeypatch.setattr(th.config, "repo_root", repo_root)
    return data_root / "scaling_overrides.json", repo_root / "data" / "scaling_overrides.json"


def test_repo_only_symbol_kept_when_data_root_table_lacks_it(monkeypatch, tmp_path, gbp_metadata):
    """SGLN is only in the repo table; the DATA_ROOT table must not drop it."""
    data_file, repo_file = _point_at(
        monkeypatch, tmp_path, data_table={"L": {"BP": 0.01}}, repo_table={"L": {"SGLN": 0.01}}
    )

    assert th._scaling_override_paths() == [repo_file, data_file]
    assert th.get_scaling_override("SGLN.L", "L", None) == pytest.approx(0.01)
    assert th.get_scaling_override("BP.L", "L", None) == pytest.approx(0.01)


def test_data_root_entry_overrides_repo_entry_for_same_symbol(monkeypatch, tmp_path, gbp_metadata):
    _point_at(monkeypatch, tmp_path, data_table={"L": {"ERNS": 1}}, repo_table={"L": {"ERNS": 0.01, "GSK": 0.01}})

    merged, _sources = th._load_scaling_overrides()
    assert merged == {"L": {"ERNS": 1, "GSK": 0.01}}
    assert th.get_scaling_override("ERNS.L", "L", None) == pytest.approx(1.0)
    assert th.get_scaling_override("GSK.L", "L", None) == pytest.approx(0.01)


def test_data_root_sections_merge_case_insensitively(monkeypatch, tmp_path, gbp_metadata):
    _point_at(monkeypatch, tmp_path, data_table={"l": {"BP": 0.01}}, repo_table={"L": {"SGLN": 0.01}})

    merged, _sources = th._load_scaling_overrides()
    assert merged == {"L": {"SGLN": 0.01, "BP": 0.01}}


def test_only_data_root_table_present(monkeypatch, tmp_path, gbp_metadata):
    data_file, _repo_file = _point_at(monkeypatch, tmp_path, data_table={"L": {"BP": 0.01}})

    assert th._scaling_override_paths() == ([BUNDLED, data_file] if BUNDLED.exists() else [data_file])
    assert th.get_scaling_override("BP.L", "L", None) == pytest.approx(0.01)


def test_only_repo_table_present(monkeypatch, tmp_path, gbp_metadata):
    _data_file, repo_file = _point_at(monkeypatch, tmp_path, repo_table={"L": {"BP": 0.01}})

    assert th._scaling_override_paths() == [repo_file]
    assert th.get_scaling_override("BP.L", "L", None) == pytest.approx(0.01)


def test_same_file_for_data_root_and_repo_is_read_once(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    _write_overrides(repo_root / "data", {"L": {"BP": 0.01}})
    monkeypatch.setattr(th.config, "repo_root", repo_root)
    monkeypatch.setattr(th.config, "data_root", repo_root / "data")

    assert th._scaling_override_paths() == [repo_root / "data" / "scaling_overrides.json"]


# Shaped like allotmint-data/scaling_overrides.json: one big "L" section that
# includes the tickers #7787 named, plus the non-pence factors it carries.
ALLOTMINT_DATA_SHAPED = {
    "L": {
        "GAMA": 0.01,
        "ADM": 0.01,
        "AZN": 0.01,
        "AV": 0.01,
        "BP": 0.01,
        "SN": 0.01,
        "VOD": 0.01,
        "ERNS": 1,
        "IE00BYV1RG46": 100,
    }
}


@pytest.mark.parametrize("ticker", ["BP.L", "AZN.L", "SN.L"])
def test_data_root_shaped_table_scales_named_tickers(monkeypatch, tmp_path, gbp_metadata, ticker):
    """Regression for #7787: the repo copy (which lacks these) must not shadow DATA_ROOT."""
    _point_at(monkeypatch, tmp_path, data_table=ALLOTMINT_DATA_SHAPED, repo_table={"L": {"SGLN": 0.01}})

    assert th.get_scaling_override(ticker, "L", None) == pytest.approx(0.01)
    assert th.get_scaling_override(ticker, "", None) == pytest.approx(0.01)


@pytest.mark.parametrize("ticker", ["AV", "AV.", "AV.L"])
def test_l_override_applies_without_explicit_exchange(monkeypatch, tmp_path, gbp_metadata, ticker):
    _write_overrides(tmp_path, {"L": {"AV": 0.01}})
    monkeypatch.setattr(th.config, "data_root", tmp_path)

    assert th.get_scaling_override(ticker, "", None) == pytest.approx(0.01)


def test_inferred_exchange_prefers_suffix_and_rejects_ambiguity():
    table = {"L": {"ABC": 0.01, "XYZ": 0.01}, "N": {"ABC": 1, "XYZ": 1}, "*": {"AV": 2}}
    assert th._infer_override_exchange("XYZ.N", "XYZ", table) == "N"
    assert th._infer_override_exchange("ABC", "ABC", table) == ""
    assert th._infer_override_exchange("AV.", "AV", table) == ""
    assert th._infer_override_exchange("AV.", "AV", {"L": {"AV": 0.01}}) == "L"


def test_inferred_exchange_ignores_share_class_suffix():
    """``BRK.B`` / ``BF.B`` are share classes, not a ``"B"`` exchange."""
    table = {"B": {"OTHER": 0.01}, "L": {"ADM": 0.01, "AV": 0.01}}
    assert th._infer_override_exchange("BRK.B", "BRK", table) == ""
    assert th._infer_override_exchange("BF.B", "BF", table) == ""
    # A real exchange suffix whose section lists the symbol still wins.
    assert th._infer_override_exchange("ADM.L", "ADM", table) == "L"
    # Padded EPIC: no usable suffix, single section lists the symbol.
    assert th._infer_override_exchange("AV.", "AV", table) == "L"


def test_suffix_without_matching_section_falls_back_to_table_lookup():
    # "Z" has no section, so the single section listing XYZ is used.
    assert th._infer_override_exchange("XYZ.Z", "XYZ", {"L": {"XYZ": 0.01}}) == "L"
    # The "*" section is never returned as an exchange.
    assert th._infer_override_exchange("AV.*", "AV", {"*": {"AV": 0.01}}) == ""


def test_trailing_dot_ticker_listed_in_two_sections_is_ambiguous():
    """``"AV."`` has an empty suffix, so only the table lookup applies to it."""
    assert th._infer_override_exchange("AV.", "AV", {"L": {"AV": 0.01}, "N": {"AV": 1}}) == ""


def test_section_key_case_is_consistent_between_branches():
    table = {"l": {"ADM": 0.01}}
    assert th._infer_override_exchange("ADM.L", "ADM", table) == "L"
    assert th._infer_override_exchange("ADM.", "ADM", table) == "L"


def test_share_class_ticker_not_scaled_by_unrelated_section(monkeypatch, tmp_path, gbp_metadata):
    _write_overrides(tmp_path, {"B": {"OTHER": 0.01}})
    monkeypatch.setattr(th.config, "data_root", tmp_path)

    assert th.get_scaling_override("BRK.B", "", None) == pytest.approx(1.0)


def test_bundled_copy_used_when_no_configured_table(monkeypatch, tmp_path):
    monkeypatch.setattr(th.config, "data_root", None)
    monkeypatch.setattr(th.config, "repo_root", None)
    assert th._scaling_override_paths() == [BUNDLED]

    monkeypatch.setattr(th.config, "data_root", tmp_path / "no-data-root")
    monkeypatch.setattr(th.config, "repo_root", tmp_path / "no-repo-root")
    assert th._scaling_override_paths() == [BUNDLED]
