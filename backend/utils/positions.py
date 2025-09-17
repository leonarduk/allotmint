import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from typing import Union

import pandas as pd

# ------------------------------------------------------------------ #
#  Public helpers
# ------------------------------------------------------------------ #


def get_unique_tickers(xml_file: str, cutoff_date: Union[str, datetime, None] = None) -> list[str]:
    df = extract_holdings_from_transactions(xml_file, by_account=False, cutoff_date=cutoff_date)
    return df["ticker"].dropna().unique().tolist()


def extract_holdings_from_transactions(
    xml_file: str,
    *,
    by_account: bool = False,
    cutoff_date: Union[str, datetime, None] = None,
) -> pd.DataFrame:
    """
    Rebuild position sizes from <portfolio-transaction> entries.

    - Supports BUY, SELL, TRANSFER_IN / OUT, REMOVAL (unit-moving types)
    - Converts PP's raw <shares> (scaled by 1e8) to real units
    - Works with or without per-account breakdown
    - Adds acquired_date: most recent BUY or TRANSFER_IN per security
    """

    SHARE_SCALE = 10**8
    TYPE_SIGN = {
        "BUY": 1,
        "SELL": -1,
        "TRANSFER_IN": 1,
        "TRANSFER_OUT": -1,
        "REMOVAL": -1,
    }

    tree = ET.parse(xml_file)
    root = tree.getroot()

    # ---- cutoff to datetime --------------------------------------------
    if isinstance(cutoff_date, str):
        cutoff_date = datetime.strptime(cutoff_date, "%Y-%m-%d")

    def _date_ok(iso: str | None) -> bool:
        if cutoff_date is None or not iso:
            return True
        return datetime.strptime(iso[:10], "%Y-%m-%d") <= cutoff_date

    # ---- securityId ➜ meta --------------------------------------------
    sec_meta = {}
    for s in root.findall(".//securities/security"):
        sid = s.attrib.get("id") or s.findtext("uuid")
        if not sid:
            continue
        sec_meta[sid] = {
            "name": s.findtext("name", ""),
            "isin": s.findtext("isin", ""),
            "ticker": s.findtext("tickerSymbol", ""),
        }

    # ---- iterate -------------------------------------------------------
    ledgers: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    acquisition_dates: dict[str, dict[str, str]] = defaultdict(dict)  # acct_name -> sid -> most recent acquisition date

    account_nodes = root.findall(".//account") if by_account else [root]

    for account in account_nodes:
        acct_name = account.findtext("name", "Portfolio") if by_account else ""

        for ptx in account.findall(".//portfolio-transaction"):
            date_str = ptx.findtext("date")
            if not _date_ok(date_str):
                continue

            ttype = ptx.findtext("type", "").strip()
            sign = TYPE_SIGN.get(ttype)
            if sign is None:
                continue  # skip dividends, fees, etc.

            q_raw = ptx.findtext("shares") or ptx.findtext("units")
            if not q_raw:
                continue
            try:
                qty = float(q_raw) / SHARE_SCALE * sign
            except ValueError:
                continue

            sid_elem = ptx.find("security")
            if sid_elem is None:
                continue
            sid = sid_elem.attrib.get("reference")
            if not sid:
                continue

            # Update quantity
            ledgers[acct_name][sid] += qty

            # Track most recent acquisition date
            if ttype in ("BUY", "TRANSFER_IN") and date_str:
                existing = acquisition_dates[acct_name].get(sid)
                if (not existing) or (date_str > existing):
                    acquisition_dates[acct_name][sid] = date_str

    # ---- flatten to DataFrame -----------------------------------------
    rows = []
    for acct, ldg in ledgers.items():
        for sid, qty in ldg.items():
            if abs(qty) < 1e-9:
                continue
            meta = sec_meta.get(sid, {})
            acq_date = acquisition_dates.get(acct, {}).get(sid, "")
            rows.append(
                {
                    "account": acct,
                    "securityId": sid,
                    "name": meta.get("name", ""),
                    "ticker": meta.get("ticker", ""),
                    "isin": meta.get("isin", ""),
                    "quantity": qty,
                    "acquired_date": acq_date,
                }
            )

    return pd.DataFrame(rows)


def extract_dividends_from_transactions(
    xml_file: str,
    *,
    by_account: bool = False,
    cutoff_date: Union[str, datetime, None] = None,
) -> pd.DataFrame:
    """Return dividend payouts from ``<portfolio-transaction>`` entries.

    The resulting DataFrame has one row per dividend with columns:

    - account: optional account name if ``by_account`` is True
    - securityId / name / ticker / isin: instrument metadata
    - date: payout date (ISO string)
    - amount_minor: dividend amount in minor currency units
    """

    tree = ET.parse(xml_file)
    root = tree.getroot()

    if isinstance(cutoff_date, str):
        cutoff_date = datetime.strptime(cutoff_date, "%Y-%m-%d")

    def _date_ok(iso: str | None) -> bool:
        if cutoff_date is None or not iso:
            return True
        return datetime.strptime(iso[:10], "%Y-%m-%d") <= cutoff_date

    sec_meta = {}
    for s in root.findall(".//securities/security"):
        sid = s.attrib.get("id") or s.findtext("uuid")
        if not sid:
            continue
        sec_meta[sid] = {
            "name": s.findtext("name", ""),
            "isin": s.findtext("isin", ""),
            "ticker": s.findtext("tickerSymbol", ""),
        }

    account_nodes = root.findall(".//account") if by_account else [root]

    rows = []
    for account in account_nodes:
        acct_name = account.findtext("name", "Portfolio") if by_account else ""

        for ptx in account.findall(".//portfolio-transaction"):
            ttype = ptx.findtext("type", "").strip()
            if ttype != "DIVIDEND":
                continue

            date_str = ptx.findtext("date")
            if not _date_ok(date_str):
                continue

            amount_raw = ptx.findtext("amount")
            if not amount_raw:
                continue
            try:
                amount_minor = float(amount_raw)
            except ValueError:
                continue

            sid_elem = ptx.find("security")
            if sid_elem is None:
                continue
            sid = sid_elem.attrib.get("reference")
            if not sid:
                continue
            meta = sec_meta.get(sid, {})

            rows.append(
                {
                    "account": acct_name,
                    "securityId": sid,
                    "name": meta.get("name", ""),
                    "ticker": meta.get("ticker", ""),
                    "isin": meta.get("isin", ""),
                    "date": date_str or "",
                    "amount_minor": amount_minor,
                }
            )

    return pd.DataFrame(rows)


def get_name_map_from_xml(xml_file: str) -> dict[str, str]:
    tree = ET.parse(xml_file)
    root = tree.getroot()

    out = {}
    for s in root.findall(".//securities/security"):
        isin = s.findtext("isin", "").strip()
        ticker = s.findtext("tickerSymbol", "").strip()
        name = s.findtext("name", "").strip()
        if isin:
            out[isin] = f"{name} ({ticker})" if ticker else name
        if ticker:
            out[ticker] = f"{name} ({ticker})"
    return out


# ------------------------------------------------------------------ #
#  Quick CLI test
# ------------------------------------------------------------------ #
if __name__ == "__main__":  # pragma: no cover
    xml = r"C:/workspaces/bitbucket/luk/data/portfolio/investments-with-id.xml"  # pragma: no cover
    df = extract_holdings_from_transactions(xml, by_account=True)  # pragma: no cover
    print(f"\nRebuilt {len(df)} positions")  # pragma: no cover

    pd.set_option("display.max_rows", None)  # pragma: no cover
    print(df.to_string(index=False, formatters={"quantity": "{:,.4f}".format}))  # pragma: no cover
