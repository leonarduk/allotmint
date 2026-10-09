"""A temporary instruments catalogue, audit file and upkeep store (shared with tests/backend/routes)."""

from __future__ import annotations

import json

import backend.routes.instrument_admin as instrument_admin
from backend.common import instruments
from backend.data_quality import audit
from backend.fund_upkeep import charges_agent, look_through_upkeep, proposals, storage

FUND_META = {"ticker": "FUNDX.L", "name": "Example Global Fund", "instrumentType": "ETF", "isin": "GB00EXAMPLE1"}


def make_catalogue(tmp_path, monkeypatch):
    """``tmp_path/instruments`` holding one synthetic fund, wired into every reader/writer used here."""
    root = tmp_path / "instruments"
    (root / "L").mkdir(parents=True)
    (root / "L" / "FUNDX.json").write_text(json.dumps(FUND_META, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", root)
    monkeypatch.setattr(instruments, "_s3_location", lambda: None)
    # Other tests reload backend.common.instruments; bind every importer to the patched module.
    for module in (instrument_admin, proposals, charges_agent, look_through_upkeep):
        monkeypatch.setattr(module, "get_instrument_meta", instruments.get_instrument_meta)
    monkeypatch.setattr(instrument_admin, "save_instrument_meta", instruments.save_instrument_meta)
    monkeypatch.setattr(instrument_admin, "instrument_meta_path", instruments.instrument_meta_path)
    monkeypatch.setattr(storage, "store_dir", lambda: tmp_path / "fund_upkeep")
    monkeypatch.setattr(audit, "audit_path", lambda: tmp_path / "audit" / "audit.jsonl")
    instruments.get_instrument_meta.cache_clear()
    return root


def stored_meta(root, symbol="FUNDX"):
    return json.loads((root / "L" / f"{symbol}.json").read_text(encoding="utf-8"))
