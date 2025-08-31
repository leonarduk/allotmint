import pytest
from backend.utils.positions import (
    extract_holdings_from_transactions,
    get_unique_tickers,
    get_name_map_from_xml,
)


@pytest.fixture
def portfolio_xml(tmp_path):
    xml = """
<root>
  <securities>
    <security id="sec1">
      <name>Foo Corp</name>
      <isin>US0000001</isin>
      <tickerSymbol>FOO</tickerSymbol>
    </security>
    <security id="sec2">
      <name>Bar Inc</name>
      <isin>US0000002</isin>
      <tickerSymbol>BAR</tickerSymbol>
    </security>
  </securities>
  <accounts>
    <account>
      <name>A</name>
      <portfolio-transaction>
        <date>2023-01-01</date>
        <type>BUY</type>
        <shares>100000000</shares>
        <security reference="sec1" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date>2023-01-05</date>
        <type>SELL</type>
        <shares>20000000</shares>
        <security reference="sec1" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date>2023-01-10</date>
        <type>BUY</type>
        <shares>BAD</shares>
        <security reference="sec1" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date></date>
        <type>BUY</type>
        <shares>10000000</shares>
        <security reference="sec1" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date>2023-02-01</date>
        <type>BUY</type>
        <shares>300000000</shares>
        <security reference="sec2" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date>2023-03-01</date>
        <type>SELL</type>
        <shares>100000000</shares>
        <security reference="sec2" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date>2023-04-01</date>
        <type>TRANSFER_IN</type>
        <shares>50000000</shares>
        <security reference="sec2" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date>2023-05-01</date>
        <type>TRANSFER_OUT</type>
        <shares>20000000</shares>
        <security reference="sec2" />
      </portfolio-transaction>
    </account>
    <account>
      <name>B</name>
      <portfolio-transaction>
        <date>2023-02-10</date>
        <type>BUY</type>
        <shares>100000000</shares>
        <security reference="sec2" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date>2023-02-20</date>
        <type>SELL</type>
        <shares>20000000</shares>
        <security reference="sec2" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date>2023-03-01</date>
        <type>TRANSFER_IN</type>
        <shares>50000000</shares>
        <security reference="sec1" />
      </portfolio-transaction>
      <portfolio-transaction>
        <date>2023-03-10</date>
        <type>TRANSFER_OUT</type>
        <shares>10000000</shares>
        <security reference="sec1" />
      </portfolio-transaction>
    </account>
  </accounts>
</root>
"""
    path = tmp_path / "portfolio.xml"
    path.write_text(xml)
    return path


def _records_by_ticker(df):
    return {row["ticker"]: row for _, row in df.iterrows()}


def test_extract_holdings_sums_and_acquisitions(portfolio_xml):
    df = extract_holdings_from_transactions(portfolio_xml)
    rec = _records_by_ticker(df)
    assert pytest.approx(rec["FOO"]["quantity"]) == 1.3
    assert rec["FOO"]["acquired_date"] == "2023-03-01"
    assert pytest.approx(rec["BAR"]["quantity"]) == 3.1
    assert rec["BAR"]["acquired_date"] == "2023-04-01"


def test_extract_holdings_by_account(portfolio_xml):
    df = extract_holdings_from_transactions(portfolio_xml, by_account=True)
    rec = {(r["account"], r["ticker"]): r for _, r in df.iterrows()}
    assert pytest.approx(rec[("A", "FOO")]["quantity"]) == 0.9
    assert rec[("A", "FOO")]["acquired_date"] == "2023-01-01"
    assert pytest.approx(rec[("A", "BAR")]["quantity"]) == 2.3
    assert rec[("A", "BAR")]["acquired_date"] == "2023-04-01"
    assert pytest.approx(rec[("B", "FOO")]["quantity"]) == 0.4
    assert rec[("B", "FOO")]["acquired_date"] == "2023-03-01"
    assert pytest.approx(rec[("B", "BAR")]["quantity"]) == 0.8
    assert rec[("B", "BAR")]["acquired_date"] == "2023-02-10"


def test_extract_holdings_with_cutoff(portfolio_xml):
    df = extract_holdings_from_transactions(portfolio_xml, cutoff_date="2023-02-15")
    rec = _records_by_ticker(df)
    assert pytest.approx(rec["FOO"]["quantity"]) == 0.9
    assert rec["FOO"]["acquired_date"] == "2023-01-01"
    assert pytest.approx(rec["BAR"]["quantity"]) == 4.0
    assert rec["BAR"]["acquired_date"] == "2023-02-10"


def test_get_unique_tickers(portfolio_xml):
    assert set(get_unique_tickers(portfolio_xml)) == {"FOO", "BAR"}
    assert set(get_unique_tickers(portfolio_xml, cutoff_date="2023-01-31")) == {"FOO"}


def test_get_name_map_from_xml(portfolio_xml):
    name_map = get_name_map_from_xml(portfolio_xml)
    assert name_map["US0000001"] == "Foo Corp (FOO)"
    assert name_map["FOO"] == "Foo Corp (FOO)"
    assert name_map["US0000002"] == "Bar Inc (BAR)"
    assert name_map["BAR"] == "Bar Inc (BAR)"
