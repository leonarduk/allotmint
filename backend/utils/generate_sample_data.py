import json
import os
from datetime import date
from pathlib import Path

from positions import extract_holdings_from_transactions


def normalize_account(account: str) -> tuple[str, str]:
    """
    Split 'Alex ISA Cash' → ('alex', 'isa')
    """
    parts = account.strip().split()
    if len(parts) >= 2:
        return parts[0].lower(), parts[1].lower()
    return "unknown", "unknown"


def generate_json_holdings(xml_path: str, output_base_dir: str):
    df = extract_holdings_from_transactions(xml_path, by_account=True)

    # Add 'owner' and 'account_type' from account column
    df["owner"], df["account_type"] = zip(*df["account"].map(normalize_account))
    grouped = df.groupby(["owner", "account_type"])
    today = str(date.today())

    for (owner, account_type), group in grouped:
        output = {
            "owner": owner,
            "account_type": account_type.upper(),
            "currency": "GBP",
            "last_updated": today,
            "holdings": []
        }

        for _, row in group.iterrows():
            from datetime import datetime

            acq_date_raw = row.get("acquired_date", "")
            try:
                acq_date = datetime.fromisoformat(acq_date_raw)
                days_held = (datetime.today() - acq_date).days
                sell_eligible = days_held >= 30
                days_until_eligible = None if sell_eligible else max(0, 30 - days_held)
            except Exception:
                days_held = None
                sell_eligible = False
                days_until_eligible = None

            holding = {
                "ticker": row["ticker"],
                "name": row["name"],
                "units": round(row["quantity"], 4),
                "acquired_date": acq_date_raw,
                "days_held": days_held,
                "sell_eligible": sell_eligible,
                "days_until_eligible": days_until_eligible,
                "price": 0.0,
                "cost_basis_gbp": 0.0,
                "market_value_gbp": 0.0,
                "gain_gbp": 0.0,
            }

            output["holdings"].append(holding)

        # Save to: data-sample/accounts/{owner}/{isa|sipp}.json
        target_dir = Path(output_base_dir) / owner
        os.makedirs(target_dir, exist_ok=True)

        out_file = target_dir / f"{account_type}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"✅ Wrote {out_file} ({len(output['holdings'])} holdings)")


if __name__ == "__main__":
    xml = "C:/workspaces/bitbucket/luk/data/portfolio/investments-with-id.xml"
    output_root = "C:/workspaces/github/allotmint/data/accounts"
    generate_json_holdings(xml, output_root)
