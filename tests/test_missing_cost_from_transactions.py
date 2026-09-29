import json

from backend.common.holdings_rebuild import transaction_cost_hints
from backend.common.portfolio import _fill_missing_costs

TXS = [
    {"date": "2021-09-26", "ticker": "ADM.L", "type": "TRANSFER_IN", "units": 73.0},
    {"date": "2022-01-10", "ticker": "ADM.L", "type": "BUY", "units": 5.0, "price_gbp": 20.0},
    {"date": "2022-02-01", "ticker": "KO.N", "type": "BUY", "units": 3.0, "price_gbp": 50.0},
    {"date": "2021-09-26", "ticker": "GONE.L", "type": "TRANSFER_IN", "units": 4.0},
    {"date": "2022-03-01", "ticker": "GONE.L", "type": "SELL", "units": 4.0, "price_gbp": 9.0},
]


def test_fill_dates_zero_cost_holdings_from_transfer_in(tmp_path):
    owner_dir = tmp_path / "steve"
    owner_dir.mkdir()
    (owner_dir / "SIPP_transactions.json").write_text(json.dumps({"transactions": TXS}))
    holdings = [
        {"ticker": "ADM.L", "units": 78.0, "cost_basis_gbp": 0.0},
        {"ticker": "KO.N", "units": 3.0, "cost_basis_gbp": 150.0},
        {"ticker": "ADM.L", "units": 1.0, "cost_basis_gbp": 0.0, "acquired_date": "2020-01-01"},
        {"ticker": "KO.N", "units": 3.0, "cost_basis_gbp": 0.0},
    ]
    _fill_missing_costs("steve", "sipp", holdings, tmp_path)
    assert holdings[0]["acquired_date"] == "2021-09-26"
    assert "acquired_date" not in holdings[1]
    assert holdings[1]["cost_basis_gbp"] == 150.0
    assert holdings[2]["acquired_date"] == "2020-01-01"
    assert holdings[3]["cost_basis_gbp"] == 150.0
    assert "acquired_date" not in holdings[3]


def test_fill_is_a_noop_without_a_transactions_file(tmp_path):
    (tmp_path / "steve").mkdir()
    holdings = [{"ticker": "ADM.L", "units": 1.0, "cost_basis_gbp": 0.0}]
    _fill_missing_costs("steve", "isa", holdings, tmp_path)
    assert "acquired_date" not in holdings[0]
