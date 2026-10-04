"""Tests for scripts/classify_instruments.py (#9196)."""

from __future__ import annotations

import json

from scripts import classify_instruments


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _instruments(tmp_path):
    root = tmp_path / "instruments"
    _write(
        root / "L" / "VWRL.json",
        {
            "ticker": "VWRL.L",
            "name": "Vanguard FTSE All-World UCITS ETF (GBP)",
            "instrumentType": "ETF",
            "sector": "Financials",
        },
    )
    _write(root / "L" / "ESIH.json", {"name": "iShares MSCI EUR HealthCare UCITS ETF", "instrumentType": "ETF"})
    _write(root / "L" / "GSK.json", {"ticker": "GSK.L", "name": "GSK plc", "asset_class": "equity"})
    _write(root / "Cash" / "GBP.json", {"name": "Cash (GBP)", "sector": "Cash"})
    _write(root / "groupings" / "income.json", {"id": "income", "name": "Income"})
    (root / "L" / "BROKEN.json").write_text("{", encoding="utf-8")
    return root


def test_dry_run_reports_without_writing(tmp_path) -> None:
    root = _instruments(tmp_path)
    before = (root / "L" / "VWRL.json").read_text(encoding="utf-8")

    report = classify_instruments.classify_all(root, {})

    assert report["L/VWRL.json"] == {"asset_class": (None, "equity"), "sector": ("Financials", "Multi-sector")}
    assert report["Cash/GBP.json"] == {"asset_class": (None, "cash")}
    assert "L/GSK.json" not in report  # already classified
    assert not any(key.startswith("groupings/") for key in report)
    assert (root / "L" / "VWRL.json").read_text(encoding="utf-8") == before


def test_write_applies_overrides_and_keeps_key_order(tmp_path) -> None:
    root = _instruments(tmp_path)
    overrides = {"ESIH.L": {"sector": "Health Care"}}

    classify_instruments.classify_all(root, overrides, write=True)

    vwrl = json.loads((root / "L" / "VWRL.json").read_text(encoding="utf-8"))
    assert list(vwrl) == ["ticker", "name", "instrumentType", "sector", "asset_class"]
    assert vwrl["sector"] == "Multi-sector"
    esih = json.loads((root / "L" / "ESIH.json").read_text(encoding="utf-8"))
    assert esih == {
        "name": "iShares MSCI EUR HealthCare UCITS ETF",
        "instrumentType": "ETF",
        "asset_class": "equity",
        "sector": "Health Care",
    }
    # A second run is a no-op.
    assert classify_instruments.classify_all(root, overrides) == {}


def test_main_reads_overrides_file(tmp_path, capsys) -> None:
    root = _instruments(tmp_path)
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"ESIH.L": {"sector": "Health Care"}}), encoding="utf-8")

    assert classify_instruments.main(["--instruments-dir", str(root), "--overrides", str(overrides)]) == 0

    out = capsys.readouterr().out
    assert "L/ESIH.json: asset_class: None -> 'equity'; sector: None -> 'Health Care'" in out
    assert "Would update 3 file(s)" in out
