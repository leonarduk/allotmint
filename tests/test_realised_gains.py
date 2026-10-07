import json
import logging

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.realised_gains import compute_disposal_gains
from backend.config import config
from backend.utils.convert_portfolio_xml_to_account_transactions import extract_transactions_by_account


def _buy(date, units, amount, ticker="AAA.L"):
    return {"date": date, "type": "BUY", "ticker": ticker, "units": units, "amount_minor": amount * 100}


def _sell(date, units, amount, ticker="AAA.L"):
    return {"date": date, "type": "SELL", "ticker": ticker, "units": units, "amount_minor": amount * 100}


def test_full_disposal_gain_is_proceeds_minus_cost():
    gains = compute_disposal_gains([_buy("2024-01-01", 10, 1000), _sell("2024-06-01", 10, 1250)])
    assert gains[1].realised_gain_gbp == pytest.approx(250.0)
    assert gains[1].cost_basis_gbp == pytest.approx(1000.0)
    assert gains[1].proceeds_gbp == pytest.approx(1250.0)
    assert gains[1].unmatched_units == 0.0


def test_partial_disposal_uses_average_pool_cost():
    txs = [
        _buy("2024-01-01", 100, 1000),
        _buy("2024-02-01", 100, 3000),  # pool: 200 units, £4000 -> £20/unit
        _sell("2024-03-01", 50, 900),
        _sell("2024-04-01", 150, 2400),
    ]
    gains = compute_disposal_gains(txs)
    assert gains[2].cost_basis_gbp == pytest.approx(1000.0)
    assert gains[2].realised_gain_gbp == pytest.approx(-100.0)
    assert gains[3].cost_basis_gbp == pytest.approx(3000.0)
    assert gains[3].realised_gain_gbp == pytest.approx(-600.0)


def test_input_order_does_not_matter_and_same_day_buy_precedes_sell():
    txs = [_sell("2024-01-01", 10, 1100), _buy("2024-01-01", 10, 1000)]
    gains = compute_disposal_gains(txs)
    assert gains[0].realised_gain_gbp == pytest.approx(100.0)
    assert 1 not in gains


def test_selling_more_than_recorded_leaves_gain_unknown():
    gains = compute_disposal_gains([_buy("2024-01-01", 78, 2482.56), _sell("2024-01-01", 156, 4938.79)])
    assert gains[1].realised_gain_gbp is None
    assert gains[1].unmatched_units == pytest.approx(78)
    assert gains[1].cost_basis_gbp == pytest.approx(2482.56)


def test_transfer_in_without_cost_makes_pooled_disposal_unknown():
    txs = [
        {"date": "2021-09-26", "type": "TRANSFER_IN", "ticker": "AAA.L", "units": 50},
        _buy("2022-01-01", 50, 500),
        _sell("2022-02-01", 20, 300),
    ]
    gains = compute_disposal_gains(txs)
    assert gains[2].realised_gain_gbp is None
    assert gains[2].unmatched_units == pytest.approx(10)
    assert gains[2].cost_basis_gbp == pytest.approx(100.0)


def test_falls_back_to_price_and_fees_and_groups_by_name_without_ticker():
    txs = [
        {"date": "2024-01-01", "type": "BUY", "instrument_name": "Some Fund", "units": 10, "price_gbp": 10, "fees": 5},
        {"date": "2024-02-01", "type": "SELL", "instrument_name": "Some Fund", "units": 10, "price_gbp": 12, "fees": 5},
    ]
    gains = compute_disposal_gains(txs)
    assert gains[1].cost_basis_gbp == pytest.approx(105.0)
    assert gains[1].proceeds_gbp == pytest.approx(115.0)
    assert gains[1].realised_gain_gbp == pytest.approx(10.0)


def test_amount_minor_is_net_of_fees_so_fees_are_not_deducted_again():
    # Convention (#7967): ``amount_minor`` is the settled cash, already net of
    # fees -- the total paid on a BUY and the proceeds received on a SELL, as
    # Portfolio Performance exports it.  ``fees`` alongside it is informational
    # and must not be subtracted a second time.
    txs = [
        {"date": "2024-01-01", "type": "BUY", "ticker": "AAA.L", "units": 10, "amount_minor": 10500, "fees": 5},
        {"date": "2024-02-01", "type": "SELL", "ticker": "AAA.L", "units": 10, "amount_minor": 11500, "fees": 5},
    ]
    gains = compute_disposal_gains(txs)
    assert gains[1].cost_basis_gbp == pytest.approx(105.0)
    assert gains[1].proceeds_gbp == pytest.approx(115.0)
    assert gains[1].realised_gain_gbp == pytest.approx(10.0)


def test_amount_minor_and_price_fallback_agree_on_net_proceeds():
    # The same trade recorded either way (settled amount, or gross price x
    # units with fees) must realise the same gain.
    fallback = [
        {"date": "2024-01-01", "type": "BUY", "ticker": "AAA.L", "units": 10, "price_gbp": 10, "fees": 5},
        {"date": "2024-02-01", "type": "SELL", "ticker": "AAA.L", "units": 10, "price_gbp": 12, "fees": 5},
    ]
    settled = [
        {**fallback[0], "amount_minor": 10500},
        {**fallback[1], "amount_minor": 11500},
    ]
    assert compute_disposal_gains(settled)[1] == compute_disposal_gains(fallback)[1]


def test_amount_minor_wins_over_price_and_fees_when_they_disagree():
    # When the settled ``amount_minor`` and the gross price x units +/- fees
    # figure disagree, ``amount_minor`` is used as-is: neither ``price_gbp``
    # nor ``fees`` alters it, so fees cannot be applied twice.
    txs = [
        {
            "date": "2024-01-01",
            "type": "BUY",
            "ticker": "AAA.L",
            "units": 10,
            "amount_minor": 10000,
            "price_gbp": 999,
            "fees": 50,
        },
        {
            "date": "2024-02-01",
            "type": "SELL",
            "ticker": "AAA.L",
            "units": 10,
            "amount_minor": 12000,
            "price_gbp": 1,
            "fees": 50,
        },
    ]
    gains = compute_disposal_gains(txs)
    assert gains[1].cost_basis_gbp == pytest.approx(100.0)
    assert gains[1].proceeds_gbp == pytest.approx(120.0)
    assert gains[1].realised_gain_gbp == pytest.approx(20.0)


def test_pp_importer_writes_settled_amount_and_no_fees_on_sell(tmp_path):
    # Ingestion side of the convention: the Portfolio Performance converter
    # copies a portfolio-transaction's <amount> (the settled cash, after the
    # FEE unit) into ``amount_minor`` and never emits a ``fees`` field, so the
    # realised gain is computed from net proceeds with no further deduction.
    xml = """<?xml version='1.0' encoding='UTF-8'?>
<root>
  <securities><security id="S1"><name>Alpha</name><tickerSymbol>AAA.L</tickerSymbol></security></securities>
  <accounts><account id="a1"><name>Steve ISA Cash</name><transactions/></account></accounts>
  <portfolio id="p1">
    <name>Steve ISA Portfolio</name>
    <referenceAccount reference="a1" />
    <transactions>
      <portfolio-transaction id="pt1">
        <date>2024-01-01</date><currencyCode>GBP</currencyCode><amount>10500</amount>
        <type>BUY</type><security reference="S1" /><shares>1000000000</shares>
        <units><unit type="FEE"><amount currency="GBP" amount="500"/></unit></units>
      </portfolio-transaction>
      <portfolio-transaction id="pt2">
        <date>2024-02-01</date><currencyCode>GBP</currencyCode><amount>11500</amount>
        <type>SELL</type><security reference="S1" /><shares>1000000000</shares>
        <units><unit type="FEE"><amount currency="GBP" amount="500"/></unit></units>
      </portfolio-transaction>
    </transactions>
  </portfolio>
</root>
"""
    path = tmp_path / "pp.xml"
    path.write_text(xml)
    df = extract_transactions_by_account(str(path))
    assert "fees" not in df.columns
    records = df.to_dict(orient="records")
    assert [r["amount_minor"] for r in records] == [10500, 11500]

    gains = compute_disposal_gains(records)
    assert gains[1].cost_basis_gbp == pytest.approx(105.0)
    assert gains[1].proceeds_gbp == pytest.approx(115.0)
    assert gains[1].realised_gain_gbp == pytest.approx(10.0)


def test_instruments_are_pooled_separately_and_scaled_shares_handled():
    txs = [
        _buy("2024-01-01", 10, 100, ticker="AAA.L"),
        {"date": "2024-01-01", "type": "BUY", "ticker": "BBB.L", "shares": 10 * 10**8, "amount_minor": 50000},
        _sell("2024-02-01", 10, 80, ticker="AAA.L"),
        {"date": "2024-02-01", "type": "SELL", "ticker": "BBB.L", "shares": 5 * 10**8, "amount_minor": 30000},
    ]
    gains = compute_disposal_gains(txs)
    assert gains[2].realised_gain_gbp == pytest.approx(-20.0)
    assert gains[3].realised_gain_gbp == pytest.approx(50.0)


@pytest.mark.parametrize("units", [999_999, 1_000_000, 1_000_001, 2_000_000])
def test_units_are_never_rescaled_by_magnitude(units):
    # Selling the whole holding at a profit: an over-sell or unknown gain would
    # mean ``units`` had been divided by PP's 10^8 share scale on one side only.
    gains = compute_disposal_gains([_buy("2024-01-01", units, 1000), _sell("2024-02-01", units, 1500)])
    assert gains[1].unmatched_units == 0.0
    assert gains[1].cost_basis_gbp == pytest.approx(1000.0)
    assert gains[1].realised_gain_gbp == pytest.approx(500.0)


@pytest.mark.parametrize("shares", [999_999, 1_000_000, 1_000_001, 2_000_000])
def test_shares_are_always_pp_scaled(shares):
    # 999,999 shares is 0.00999999 units: selling that many units empties the pool.
    real_units = shares / 10**8
    txs = [
        {"date": "2024-01-01", "type": "BUY", "ticker": "AAA.L", "shares": shares, "amount_minor": 100000},
        _sell("2024-02-01", real_units / 2, 600),
        _sell("2024-03-01", real_units, 600),
    ]
    gains = compute_disposal_gains(txs)
    assert gains[1].realised_gain_gbp == pytest.approx(100.0)
    assert gains[2].cost_basis_gbp == pytest.approx(500.0)
    assert gains[2].unmatched_units == pytest.approx(real_units / 2, abs=1e-6)


def test_units_take_precedence_over_pp_shares_on_an_edited_row():
    # Editing a PP-imported trade in the app sets ``units`` but keeps ``shares``.
    edited_buy = {**_buy("2024-01-01", 10, 100), "shares": 4 * 10**8}
    gains = compute_disposal_gains([edited_buy, _sell("2024-02-01", 10, 150)])
    assert gains[1].unmatched_units == 0.0
    assert gains[1].realised_gain_gbp == pytest.approx(50.0)


def test_undated_rows_replay_after_dated_ones():
    undated_sell = {"type": "SELL", "ticker": "AAA.L", "units": 5, "amount_minor": 60000}
    gains = compute_disposal_gains([undated_sell, _buy("2024-01-01", 10, 1000)])
    assert gains[0].cost_basis_gbp == pytest.approx(500.0)
    assert gains[0].realised_gain_gbp == pytest.approx(100.0)


def test_zero_amount_transfer_in_is_unknown_cost_not_free():
    txs = [
        {"date": "2021-09-26", "type": "TRANSFER_IN", "ticker": "AAA.L", "units": 10, "amount_minor": 0},
        _sell("2022-01-01", 10, 1500),
    ]
    gains = compute_disposal_gains(txs)
    assert gains[1].realised_gain_gbp is None
    assert gains[1].unmatched_units == pytest.approx(10)


def test_ticker_less_sell_draws_on_pool_of_same_named_ticker():
    txs = [
        {**_buy("2024-01-01", 10, 1000), "instrument_name": "Some Fund Acc"},
        {"date": "2024-02-01", "type": "SELL", "instrument_name": "Some Fund Acc", "units": 10, "amount_minor": 120000},
    ]
    gains = compute_disposal_gains(txs)
    assert gains[1].realised_gain_gbp == pytest.approx(200.0)


def test_unresolved_security_refs_pool_together():
    txs = [
        {"date": "2024-01-01", "type": "BUY", "security_ref": "../../security[3]", "units": 4, "amount_minor": 40000},
        {"date": "2024-02-01", "type": "SELL", "security_ref": "../../security[3]", "units": 4, "amount_minor": 50000},
    ]
    assert compute_disposal_gains(txs)[1].realised_gain_gbp == pytest.approx(100.0)


def test_cash_rows_are_not_treated_as_disposals():
    txs = [
        {"date": "2024-01-01", "type": "TRANSFER_IN", "ticker": "CASH.GBP", "units": 100},
        {"date": "2024-02-01", "type": "SELL", "ticker": "CASH.GBP", "units": 50, "amount_minor": 5000},
    ]
    assert compute_disposal_gains(txs) == {}


def test_sell_without_amount_or_price_has_unknown_proceeds_not_zero():
    txs = [_buy("2024-01-01", 10, 1000), {"date": "2024-06-01", "type": "SELL", "ticker": "AAA.L", "units": 10}]
    gains = compute_disposal_gains(txs)
    assert gains[1].proceeds_gbp is None
    assert gains[1].realised_gain_gbp is None
    assert gains[1].cost_basis_gbp == pytest.approx(1000.0)


def test_results_are_keyed_by_original_index_when_non_mapping_rows_are_present():
    txs = [None, _buy("2024-01-01", 10, 1000), "junk", _sell("2024-06-01", 10, 1250)]
    gains = compute_disposal_gains(txs)
    assert list(gains) == [3]
    assert gains[3].realised_gain_gbp == pytest.approx(250.0)


def test_oversold_disposal_logs_no_warning(caplog):
    with caplog.at_level(logging.WARNING):
        gains = compute_disposal_gains([_sell("2024-06-01", 10, 1250)])
    assert gains[0].realised_gain_gbp is None
    assert caplog.records == []


def test_transfer_out_and_removal_reduce_pool_without_realising_a_gain():
    txs = [
        _buy("2024-01-01", 10, 1000),
        {"date": "2024-02-01", "type": "TRANSFER_OUT", "ticker": "AAA.L", "units": 4},
        {"date": "2024-03-01", "type": "REMOVAL", "ticker": "AAA.L", "units": 2},
        _sell("2024-04-01", 4, 600),
    ]
    gains = compute_disposal_gains(txs)
    assert list(gains) == [3]
    # 6 of 10 units left the pool pro rata, taking £600 of the £1000 cost with them.
    assert gains[3].cost_basis_gbp == pytest.approx(400.0)
    assert gains[3].realised_gain_gbp == pytest.approx(200.0)


def test_list_transactions_includes_gain_even_when_buy_is_outside_date_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    doc = {
        "owner": "alice",
        "account_type": "ISA",
        "transactions": [
            _buy("2023-01-01", 10, 1000),
            _sell("2024-06-01", 10, 1250),
            # Stored derived values must not leak through or override the computation.
            {"date": "2024-07-01", "type": "INTEREST", "amount_minor": 500, "realised_gain_gbp": 999},
        ],
    }
    (owner_dir / "ISA_transactions.json").write_text(json.dumps(doc))
    client = TestClient(create_app())

    resp = client.get("/transactions", params={"owner": "alice", "start": "2024-01-01"})
    assert resp.status_code == 200
    rows = {row["type"]: row for row in resp.json()}
    assert set(rows) == {"SELL", "INTEREST"}
    assert rows["SELL"]["realised_gain_gbp"] == pytest.approx(250.0)
    assert rows["SELL"]["cost_basis_gbp"] == pytest.approx(1000.0)
    assert rows["INTEREST"]["realised_gain_gbp"] is None
