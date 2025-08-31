import json
import pandas as pd
import pytest

from backend.utils.convert_portfolio_xml_to_account_transactions import (
    _safe_int,
    _normalise_account_name,
    extract_transactions_by_account,
    write_account_json,
)


@pytest.fixture
def xml_fixture(tmp_path):
    xml = """<?xml version='1.0' encoding='UTF-8'?>
<root>
  <accounts>
    <account id="a1">
      <name>Steve ISA Cash</name>
      <transactions>
        <account-transaction id="t1">
          <uuid>u1</uuid>
          <date>2024-01-01</date>
          <currencyCode>GBP</currencyCode>
          <amount>1000</amount>
          <type>DEPOSIT</type>
        </account-transaction>
      </transactions>
    </account>
    <account id="a2">
      <name>Steve GIA Cash</name>
      <transactions>
        <account-transaction id="t2">
          <uuid>u2</uuid>
          <date>2024-01-02</date>
          <currencyCode>GBP</currencyCode>
          <amount>-500</amount>
          <type>WITHDRAWAL</type>
        </account-transaction>
      </transactions>
    </account>
  </accounts>
  <portfolio id="p1">
    <name>Steve ISA Portfolio</name>
    <referenceAccount reference="a1" />
    <transactions>
      <portfolio-transaction id="pt1">
        <uuid>u3</uuid>
        <date>2024-01-03</date>
        <currencyCode>GBP</currencyCode>
        <amount>1500</amount>
        <type>BUY</type>
        <security reference="S1" />
        <shares>10</shares>
      </portfolio-transaction>
    </transactions>
  </portfolio>
</root>
"""
    path = tmp_path / "pp.xml"
    path.write_text(xml)
    return str(path)


def test_safe_int():
    assert _safe_int("123") == 123
    assert _safe_int(None) is None
    assert _safe_int("abc") is None


def test_normalise_account_name():
    assert _normalise_account_name("Steve ISA Cash") == ("steve", "isa")
    assert _normalise_account_name("BadlyFormed") == ("unknown", "unknown")


def test_extract_transactions_by_account(xml_fixture):
    df = extract_transactions_by_account(xml_fixture)
    expected_cols = {
        "kind",
        "account_id",
        "account",
        "transaction_id",
        "uuid",
        "date",
        "currency",
        "amount_minor",
        "type",
        "security_ref",
        "shares",
        "portfolio_id",
        "portfolio",
    }
    assert set(df.columns) == expected_cols
    assert len(df) == 3
    assert (df["kind"] == "account").sum() == 2
    assert (df["kind"] == "portfolio").sum() == 1


def test_write_account_json(xml_fixture, tmp_path):
    df = extract_transactions_by_account(xml_fixture)
    out_dir = tmp_path / "out"
    write_account_json(df, out_dir)

    isa_path = out_dir / "steve" / "isa_transactions.json"
    gia_path = out_dir / "steve" / "gia_transactions.json"

    assert isa_path.exists()
    assert gia_path.exists()

    isa_data = json.loads(isa_path.read_text())
    gia_data = json.loads(gia_path.read_text())

    for data in (isa_data, gia_data):
        assert set(data.keys()) == {"owner", "account_type", "currency", "last_updated", "transactions"}

    assert len(isa_data["transactions"]) == 2
    assert len(gia_data["transactions"]) == 1
