#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Tuple

# === CONFIG ===
REPO_ROOT = Path(__file__).resolve().parents[2]  # adjust if needed
DATA_DIR = REPO_ROOT / "data"
ACCOUNTS_DIR = DATA_DIR / "accounts"
INSTRUMENTS_DIR = DATA_DIR / "instruments"
SCALING_FILE = DATA_DIR / "scaling_overrides.json"
# ==============

def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def split_ticker(ticker: str) -> Tuple[str, str | None]:
    if "." in ticker:
        sym, exch = ticker.rsplit(".", 1)
        return sym, exch.upper()
    return ticker, None

def best_name(a: str | None, b: str | None) -> str | None:
    if not a: return b
    if not b: return a
    return a if len(a) >= len(b) else b

def load_scaling() -> Dict[str, Dict[str, float]]:
    if SCALING_FILE.exists():
        return read_json(SCALING_FILE)
    return {}

def infer_currency(sym: str, exch: str | None, scaling: Dict[str, Dict[str, float]]) -> str | None:
    if sym == "CASH" and exch == "GBP":
        return "GBP"
    if exch == "L":
        scl = scaling.get("L", {}).get(sym)
        if scl == 0.01:
            return "GBX"
        return "GBP"
    if exch == "N":
        return "USD"
    if exch == "DE":
        return "EUR"
    return None

def build_instruments() -> Dict[str, dict]:
    scaling = load_scaling()
    instruments: Dict[str, dict] = {}
    for owner_dir in sorted(ACCOUNTS_DIR.glob("*")):
        for acct_file in owner_dir.glob("*.json"):
            try:
                acct = read_json(acct_file)
            except Exception:
                continue
            for h in acct.get("holdings", []):
                tkr = h.get("ticker")
                if not tkr:
                    continue
                if tkr == "CASH.GBP":
                    instruments.setdefault(tkr, {
                        "ticker": tkr,
                        "name": "Cash (GBP)",
                        "exchange": None,
                        "currency": "GBP"
                    })
                    continue
                sym, exch = split_ticker(tkr)
                entry = instruments.get(tkr, {"ticker": tkr})
                entry["name"] = best_name(entry.get("name"), h.get("name"))
                entry["exchange"] = exch
                ccy = infer_currency(sym, exch, scaling)
                if ccy:
                    entry["currency"] = ccy
                instruments[tkr] = entry
    return instruments

def write_instrument_files(instruments: Dict[str, dict]):
    # Special cash file
    if "CASH.GBP" in instruments:
        write_json(INSTRUMENTS_DIR / "Cash" / "GBP.json", instruments["CASH.GBP"])
    for tkr, meta in instruments.items():
        if tkr == "CASH.GBP":
            continue
        sym, exch = split_ticker(tkr)
        folder = exch if exch else "Unknown"
        out_path = INSTRUMENTS_DIR / folder / f"{sym}.json"
        write_json(out_path, {
            "ticker": tkr,
            "name": meta.get("name") or sym,
            "exchange": exch,
            "currency": meta.get("currency")
        })

def main():
    instruments = build_instruments()
    write_instrument_files(instruments)
    print(f"Created {len(instruments)} instrument files under {INSTRUMENTS_DIR}")

if __name__ == "__main__":
    main()
