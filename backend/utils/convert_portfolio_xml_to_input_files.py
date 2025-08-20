import json
import os
from datetime import date, datetime
from pathlib import Path

from positions import extract_holdings_from_transactions

from backend.common.approvals import is_approval_valid, load_approvals
from backend.common.instruments import get_instrument_meta
from backend.config import config


def normalize_account(account: str) -> tuple[str, str]:
    """
    Split 'Alex ISA Cash' -> ('alex', 'isa')
    """
    parts = account.strip().split()
    if len(parts) >= 2:
        return parts[0].lower(), parts[1].lower()
    return "unknown", "unknown"


def generate_json_holdings(xml_path: str, output_base_dir: str | Path = config.accounts_root):
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
            "holdings": [],
        }

        approvals = load_approvals(owner)

        for _, row in group.iterrows():
            acq_date_raw = row.get("acquired_date", "")
            try:
                acq_date = datetime.fromisoformat(acq_date_raw)
                days_held = (datetime.today() - acq_date).days
            except Exception:
                acq_date = None
                days_held = None

            meta_tkr = str(row.get("ticker", "")).strip().upper()
            meta = get_instrument_meta(meta_tkr)
            instr_type = (meta.get("instrumentType") or meta.get("instrument_type") or "").upper()
            exempt_tickers = {t.upper() for t in (config.approval_exempt_tickers or [])}
            exempt_types = {t.upper() for t in (config.approval_exempt_types or [])}

            needs_approval = not (meta_tkr in exempt_tickers or instr_type in exempt_types)

            approved = False
            if needs_approval:
                appr_on = approvals.get(meta_tkr)
                if appr_on:
                    approved = is_approval_valid(appr_on, date.today())

            sell_eligible = (days_held is not None and days_held >= config.hold_days_min) and (
                approved or not needs_approval
            )
            days_until_eligible = (
                None if sell_eligible else (None if days_held is None else max(0, config.hold_days_min - days_held))
            )

            raw_ticker = str(row.get("ticker", "")).strip()
            isin = str(row.get("isin", "")).strip().upper()

            # Heuristic: use ISIN if ticker looks like a fund (e.g. starts with "0P") or is missing
            use_isin = bool(isin) and (raw_ticker.startswith("0P") or not raw_ticker)

            holding = {
                "ticker": isin if use_isin else raw_ticker,
                "name": row.get("name", "").strip(),
                "units": round(row.get("quantity", 0.0), 4),
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

        # Save to: data/accounts/{owner}/{isa|sipp}.json
        target_dir = Path(output_base_dir) / owner
        os.makedirs(target_dir, exist_ok=True)

        out_file = target_dir / f"{account_type}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"Wrote {out_file} ({len(output['holdings'])} holdings)")


if __name__ == "__main__":
    xml = "C:/workspaces/bitbucket/luk/data/portfolio/investments-with-id.xml"
    output_root = "C:/workspaces/github/allotmint/data/accounts"
    generate_json_holdings(xml, output_root)
