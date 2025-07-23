import os
import json
from datetime import date
from pathlib import Path
from integrations.portfolioperformance.api.positions import extract_holdings_from_transactions

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
            holding = {
                "ticker": row["ticker"],
                "name": row["name"],
                "units": round(row["quantity"], 4),
                "acquired_date": "2025-06-01",      # placeholder
                "cost_basis_gbp": 0.0               # placeholder
            }
            output["holdings"].append(holding)

        # Final path: data-sample/plots/alex/isa.json
        target_dir = Path(output_base_dir) / owner
        os.makedirs(target_dir, exist_ok=True)

        out_file = target_dir / f"{account_type}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"✅ Wrote {out_file} ({len(output['holdings'])} holdings)")

if __name__ == "__main__":
    xml = "C:/workspaces/bitbucket/luk/data/portfolio/investments-with-id.xml"
    output_root = "data-sample/plots"
    generate_json_holdings(xml, output_root)
