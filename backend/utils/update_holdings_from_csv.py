#!/usr/bin/env python3
import csv
import json
from datetime import date
from pathlib import Path
from typing import Dict, Any

# ==== CONFIGURATION (edit these for your run) ====
JSON_FILE = Path(r"C:\workspaces\github\allotmint\data\accounts\steve\sipp.json")
CSV_FILE = Path(r"C:\Users\steph\Downloads\sipp.csv")
OUTPUT_FILE = JSON_FILE  # overwrite; or set to Path("C:/path/to/output.json")
PRUNE_MISSING = True     # remove tickers not in CSV
APPLY_MARKET = True      # also update price / market_value / gain
# =================================================

CSV_FIELDS = {
    "ticker": "Code",
    "name": "Stock",
    "units": "Units held",
    "cost": "Cost (£)",
    "value": "Value (£)",
    "price_pence": "Price (pence)",
}

def _num(x: str) -> float:
    if x is None:
        return 0.0
    s = str(x).strip().replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0

def read_csv(path: Path) -> Dict[str, Dict[str, Any]]:
    # Try UTF-8 first, then CP1252
    try:
        f = path.open("r", encoding="utf-8-sig", newline="")
        sample = f.read(4096)
    except UnicodeDecodeError:
        f = path.open("r", encoding="cp1252", newline="")
        sample = f.read(4096)

    f.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(f, dialect=dialect)

    rows: Dict[str, Dict[str, Any]] = {}
    for row in reader:
        ticker = (row.get(CSV_FIELDS["ticker"]) or "").strip()
        if not ticker:
            continue
        name = (row.get(CSV_FIELDS["name"]) or "").strip()
        units = _num(row.get(CSV_FIELDS["units"]))
        cost = _num(row.get(CSV_FIELDS["cost"]))
        value = _num(row.get(CSV_FIELDS["value"]))
        price_p = _num(row.get(CSV_FIELDS["price_pence"]))

        rows[ticker] = {
            "ticker": ticker,
            "name": name,
            "units": units,
            "cost_basis_gbp": cost,
            "value_gbp": value,
            "price_gbp": price_p / 100.0 if price_p else 0.0,
        }
    f.close()
    return rows

def update_json(json_in: Path, csv_in: Path, json_out: Path,
                prune_missing: bool, apply_market: bool) -> None:
    data = json.loads(json_in.read_text(encoding="utf-8"))
    csv_map = read_csv(csv_in)

    holdings = data.get("holdings", [])
    out_holdings = []
    seen = set()

    for h in holdings:
        tkr = h.get("ticker", "").strip()
        if tkr == "CASH.GBP":
            out_holdings.append(h)
            continue

        if tkr in csv_map:
            upd = csv_map[tkr]
            h["ticker"] = upd["ticker"]
            if upd["name"]:
                h["name"] = upd["name"]
            h["units"] = float(upd["units"])
            h["cost_basis_gbp"] = float(upd["cost_basis_gbp"])

            if apply_market:
                if upd["price_gbp"]:
                    h["price"] = float(upd["price_gbp"])
                if upd["value_gbp"]:
                    h["market_value_gbp"] = float(upd["value_gbp"])
                    h["gain_gbp"] = float(upd["value_gbp"]) - float(h["cost_basis_gbp"])

            seen.add(tkr)
            out_holdings.append(h)
        else:
            if not prune_missing:
                out_holdings.append(h)

    for tkr, upd in csv_map.items():
        if tkr in seen or tkr == "CASH.GBP":
            continue
        new_h = {
            "ticker": upd["ticker"],
            "name": upd["name"] or upd["ticker"],
            "units": float(upd["units"]),
            "currency": data.get("currency", "GBP"),
            "cost_basis_gbp": float(upd["cost_basis_gbp"]),
            "acquired_date": None,
            "days_held": 0,
            "sell_eligible": False,
            "days_until_eligible": 0,
            "price": 0.0,
            "market_value_gbp": 0.0,
            "gain_gbp": 0.0,
        }
        if apply_market:
            if upd["price_gbp"]:
                new_h["price"] = float(upd["price_gbp"])
            if upd["value_gbp"]:
                new_h["market_value_gbp"] = float(upd["value_gbp"])
                new_h["gain_gbp"] = float(upd["value_gbp"]) - float(new_h["cost_basis_gbp"])
        out_holdings.append(new_h)

    data["holdings"] = out_holdings
    data["last_updated"] = str(date.today())

    json_out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Updated: {json_out}")

def main():
    update_json(JSON_FILE, CSV_FILE, OUTPUT_FILE, PRUNE_MISSING, APPLY_MARKET)

if __name__ == "__main__":
    main()
