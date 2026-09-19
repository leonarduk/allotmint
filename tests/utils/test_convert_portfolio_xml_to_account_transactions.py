import json
import sys
from xml.etree.ElementTree import Element  # Element constructs test fixtures only — no parsing, safe to use stdlib here

import defusedxml
import pandas as pd
import pytest

from backend.utils.convert_portfolio_xml_to_account_transactions import (
    _get_ref,
    _normalise_account_name,
    _safe_int,
    extract_transactions_by_account,
    main,
    write_account_json,
)


@pytest.fixture
def xml_fixture(tmp_path):
    xml = """<?xml version='1.0' encoding='UTF-8'?>
<root>
  <securities>
    <security id="S1">
      <name>Adobe Inc</name>
      <isin>US00724F1012</isin>
      <tickerSymbol>ADBE.N</tickerSymbol>
    </security>
    <security id="S2">
      <name>Unlisted Holding</name>
      <isin>GB0000000000</isin>
    </security>
  </securities>
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


def test_get_ref_missing_returns_none():
    elem = Element("account-transaction")

    assert _get_ref(elem, "security") is None


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
        "ticker",
        "instrument_name",
        "isin",
        "shares",
        "portfolio_id",
        "portfolio",
    }
    assert set(df.columns) == expected_cols
    assert len(df) == 3
    assert (df["kind"] == "account").sum() == 2
    assert (df["kind"] == "portfolio").sum() == 1


def test_security_reference_is_resolved_to_a_ticker(xml_fixture):
    """The whole point of the converter for downstream consumers.

    Transactions carry only a reference to a security; without resolving it the
    output cannot be matched to an instrument.
    """
    df = extract_transactions_by_account(xml_fixture)
    trade = df[df["kind"] == "portfolio"].iloc[0]

    assert trade["security_ref"] == "S1"
    assert trade["ticker"] == "ADBE.N"
    assert trade["instrument_name"] == "Adobe Inc"
    assert trade["isin"] == "US00724F1012"


def test_cash_transactions_have_no_ticker(xml_fixture):
    df = extract_transactions_by_account(xml_fixture)
    cash = df[df["kind"] == "account"]

    assert cash["security_ref"].isna().all()
    assert cash["ticker"].isna().all()


def test_unresolved_reference_is_left_empty_rather_than_guessed(tmp_path):
    """An unknown reference must not be emitted as though it were a ticker."""
    xml = """<?xml version='1.0' encoding='UTF-8'?>
<root>
  <securities>
    <security id="S1"><name>Known</name><tickerSymbol>KNOWN.L</tickerSymbol></security>
  </securities>
  <accounts>
    <account id="a1"><name>Steve ISA Cash</name><transactions /></account>
  </accounts>
  <portfolio id="p1">
    <name>Steve ISA Portfolio</name>
    <referenceAccount reference="a1" />
    <transactions>
      <portfolio-transaction id="pt1">
        <date>2024-01-03</date>
        <type>BUY</type>
        <security reference="MISSING" />
        <shares>10</shares>
      </portfolio-transaction>
    </transactions>
  </portfolio>
</root>
"""
    path = tmp_path / "pp.xml"
    path.write_text(xml)

    df = extract_transactions_by_account(str(path))
    trade = df[df["kind"] == "portfolio"].iloc[0]

    assert trade["security_ref"] == "MISSING"
    assert trade["ticker"] is None


def test_security_without_ticker_symbol_yields_no_ticker(xml_fixture, tmp_path):
    """Some securities (unlisted funds) carry a name and ISIN but no ticker."""
    xml = tmp_path / "pp2.xml"
    original = open(xml_fixture, encoding="utf-8").read()
    xml.write_text(original.replace('<security reference="S1" />', '<security reference="S2" />'))

    df = extract_transactions_by_account(str(xml))
    trade = df[df["kind"] == "portfolio"].iloc[0]

    assert trade["ticker"] is None
    assert trade["instrument_name"] == "Unlisted Holding"
    assert trade["isin"] == "GB0000000000"


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


def test_written_json_is_valid_json(xml_fixture, tmp_path):
    """pandas missing values must not be written as the bare literal ``NaN``.

    Python's json loader tolerates it, but it is not valid JSON: browsers and
    the frontend's schema validation reject the whole payload.
    """
    df = extract_transactions_by_account(xml_fixture)
    out_dir = tmp_path / "out"
    write_account_json(df, out_dir)

    raw = (out_dir / "steve" / "isa_transactions.json").read_text(encoding="utf-8")
    assert "NaN" not in raw

    def reject_constant(name):  # pragma: no cover - only runs on failure
        raise AssertionError(f"non-JSON literal in output: {name}")

    data = json.loads(raw, parse_constant=reject_constant)

    cash = [t for t in data["transactions"] if t["kind"] == "account"]
    assert cash and all(t["ticker"] is None for t in cash)


def test_billion_laughs_xml_rejected(tmp_path):
    bomb = (
        '<?xml version="1.0"?>'
        "<!DOCTYPE lolz ["
        '  <!ENTITY lol "lol">'
        '  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
        "]>"
        "<lolz>&lol3;</lolz>"
    )
    path = tmp_path / "bomb.xml"
    path.write_text(bomb, encoding="utf-8")
    with pytest.raises(defusedxml.EntitiesForbidden):
        extract_transactions_by_account(str(path))


def test_main_errors_when_paths_missing(monkeypatch):
    # Ensure defaults are None so the CLI requires explicit arguments
    monkeypatch.setattr(
        "backend.utils.convert_portfolio_xml_to_account_transactions.config.portfolio_xml_path",
        None,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.utils.convert_portfolio_xml_to_account_transactions.config.transactions_output_root",
        None,
        raising=False,
    )

    class SentinelError(RuntimeError):
        pass

    def raise_error(self, message):  # pragma: no cover - simple shim
        raise SentinelError(message)

    monkeypatch.setattr(
        "argparse.ArgumentParser.error",
        raise_error,
    )

    monkeypatch.setattr(sys, "argv", ["prog"])

    with pytest.raises(SentinelError):
        main()


def test_main_runs_with_arguments(monkeypatch, xml_fixture, tmp_path):
    output_dir = tmp_path / "accounts"
    captured = {}

    def fake_write_account_json(df, out_root):
        captured["df"] = df.copy()
        captured["out"] = out_root

    monkeypatch.setattr(
        "backend.utils.convert_portfolio_xml_to_account_transactions.write_account_json",
        fake_write_account_json,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--xml-path",
            xml_fixture,
            "--output-root",
            str(output_dir),
        ],
    )

    main()

    expected_df = extract_transactions_by_account(xml_fixture)

    pd.testing.assert_frame_equal(captured["df"].reset_index(drop=True), expected_df.reset_index(drop=True))
    assert captured["out"] == str(output_dir)
