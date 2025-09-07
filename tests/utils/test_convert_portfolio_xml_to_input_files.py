import json
import sys
import types
from datetime import date, timedelta

import pandas as pd

positions_stub = types.ModuleType("positions")
positions_stub.extract_holdings_from_transactions = lambda *a, **k: None
sys.modules["positions"] = positions_stub

import backend.utils.convert_portfolio_xml_to_input_files as conv


def test_normalize_account_cases():
    assert conv.normalize_account("Alex ISA Cash") == ("alex", "isa")
    assert conv.normalize_account("Alex") == ("unknown", "unknown")
    assert conv.normalize_account("  Bob  SIPP  ") == ("bob", "sipp")


def test_generate_json_holdings(monkeypatch, tmp_path):
    acq_date = (date.today() - timedelta(days=10)).isoformat()
    df = pd.DataFrame(
        [
            {
                "account": "Alex ISA Cash",
                "name": "Needs Approval",
                "ticker": "NEEDS",
                "isin": "ISIN1",
                "quantity": 1.0,
                "acquired_date": acq_date,
            },
            {
                "account": "Alex ISA Cash",
                "name": "Approved",
                "ticker": "APPROVED",
                "isin": "ISIN2",
                "quantity": 2.0,
                "acquired_date": acq_date,
            },
            {
                "account": "Alex ISA Cash",
                "name": "Ticker Exempt",
                "ticker": "EXEMPTT",
                "isin": "ISIN3",
                "quantity": 3.0,
                "acquired_date": acq_date,
            },
            {
                "account": "Alex ISA Cash",
                "name": "Type Exempt 0P",
                "ticker": "0PFUND",
                "isin": "ISIN0P",
                "quantity": 4.0,
                "acquired_date": acq_date,
            },
            {
                "account": "Alex ISA Cash",
                "name": "Commodity ETF",
                "ticker": "COMETF",
                "isin": "ISIN4",
                "quantity": 5.0,
                "acquired_date": acq_date,
            },
        ]
    )

    monkeypatch.setattr(conv, "extract_holdings_from_transactions", lambda *a, **k: df)
    monkeypatch.setattr(conv, "load_approvals", lambda owner: {"APPROVED": "2024-01-01"})
    monkeypatch.setattr(conv, "is_approval_valid", lambda appr_on, today: True)

    meta = {
        "NEEDS": {"instrumentType": "STOCK"},
        "APPROVED": {"instrumentType": "STOCK"},
        "EXEMPTT": {"instrumentType": "STOCK"},
        "0PFUND": {"instrumentType": "ETF"},
        "COMETF": {"instrumentType": "ETF", "asset_class": "Commodity"},
    }
    monkeypatch.setattr(conv, "get_instrument_meta", lambda t: meta.get(t, {}))

    monkeypatch.setattr(conv.config, "approval_exempt_tickers", ["EXEMPTT"])
    monkeypatch.setattr(conv.config, "approval_exempt_types", ["ETF"])
    monkeypatch.setattr(conv.config, "hold_days_min", 5)

    conv.generate_json_holdings("dummy.xml", tmp_path)

    out_file = tmp_path / "alex" / "isa.json"
    with out_file.open() as f:
        data = json.load(f)

    assert data["owner"] == "alex"
    assert data["account_type"] == "ISA"
    assert len(data["holdings"]) == 5

    hold = {h["name"]: h for h in data["holdings"]}

    assert hold["Needs Approval"]["ticker"] == "NEEDS"
    assert hold["Needs Approval"]["sell_eligible"] is False

    assert hold["Approved"]["sell_eligible"] is True

    assert hold["Ticker Exempt"]["sell_eligible"] is True

    assert hold["Type Exempt 0P"]["ticker"] == "ISIN0P"
    assert hold["Type Exempt 0P"]["sell_eligible"] is True

    assert hold["Commodity ETF"]["sell_eligible"] is False
