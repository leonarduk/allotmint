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
    if not a:
        return b
    if not b:
        return a
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


def load_existing_instruments() -> Dict[str, Dict[str, str]]:
    """Best-effort load of existing instrument metadata from disk."""
    existing: Dict[str, Dict[str, str]] = {}
    if not INSTRUMENTS_DIR.exists():
        return existing
    for path in INSTRUMENTS_DIR.rglob("*.json"):
        try:
            data = read_json(path)
        except Exception:
            continue
        tkr = data.get("ticker")
        if not tkr:
            continue
        existing[tkr] = {
            "name": data.get("name"),
            "currency": data.get("currency"),
            "sector": data.get("sector") or data.get("Sector"),
            "region": data.get("region") or data.get("Region"),
        }
    return existing


def build_instruments() -> Dict[str, dict]:
    scaling = load_scaling()
    existing = load_existing_instruments()
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
                    existing_cash = existing.get(tkr, {})
                    instruments.setdefault(
                        tkr,
                        {
                            "ticker": tkr,
                            "name": existing_cash.get("name", "Cash (GBP)"),
                            "sector": existing_cash.get("sector"),
                            "region": existing_cash.get("region"),
                            "exchange": None,
                            "currency": existing_cash.get("currency", "GBP"),
                        },
                    )
                    continue
                sym, exch = split_ticker(tkr)
                entry = instruments.get(tkr, {"ticker": tkr})
                existing_meta = existing.get(tkr, {})
                entry["name"] = best_name(entry.get("name"), h.get("name") or existing_meta.get("name"))
                entry["exchange"] = exch
                ccy = infer_currency(sym, exch, scaling) or existing_meta.get("currency")
                if ccy:
                    entry["currency"] = ccy
                sector = h.get("sector") or existing_meta.get("sector")
                if sector and not entry.get("sector"):
                    entry["sector"] = sector
                region = h.get("region") or existing_meta.get("region")
                if region and not entry.get("region"):
                    entry["region"] = region
                instruments[tkr] = entry
    return instruments


def write_instrument_files(instruments: Dict[str, dict]):
    # Special cash file
    if "CASH.GBP" in instruments:
        meta = instruments["CASH.GBP"]
        write_json(
            INSTRUMENTS_DIR / "Cash" / "GBP.json",
            {
                "ticker": "CASH.GBP",
                "name": meta.get("name") or "Cash (GBP)",
                "sector": meta.get("sector"),
                "region": meta.get("region"),
                "exchange": meta.get("exchange"),
                "currency": meta.get("currency"),
            },
        )
    for tkr, meta in instruments.items():
        if tkr == "CASH.GBP":
            continue
        sym, exch = split_ticker(tkr)
        folder = exch if exch else "Unknown"
        out_path = INSTRUMENTS_DIR / folder / f"{sym}.json"
        write_json(
            out_path,
            {
                "ticker": tkr,
                "name": meta.get("name") or sym,
                "sector": meta.get("sector"),
                "region": meta.get("region"),
                "exchange": exch,
                "currency": meta.get("currency"),
            },
        )


def main():
    instruments = build_instruments()
    write_instrument_files(instruments)
    print(f"Created {len(instruments)} instrument files under {INSTRUMENTS_DIR}")


if __name__ == "__main__":
    main()
