"""Parsing and source fallback for fund look-through data (#9974). No network access."""

from datetime import date

import pytest
import requests

from backend.common import look_through_sources as src

TODAY = date(2026, 10, 7)


def _breakdown(values, **extra):
    return {"SalePosition": "N", "BreakdownValues": [{"Type": k, "Value": v} for k, v in values.items()], **extra}


def _snapshot(**portfolio):
    suppressed = {"Date": "2026-08-31T00:00:00", "Holdings": "Suppressed"}
    return {"Portfolios": [suppressed, {"Date": "2026-08-31T00:00:00", "Holdings": "Unsuppressed", **portfolio}]}


MIXED_FUND = _snapshot(
    AssetAllocations=[
        {"Type": "MorningStarDefault", **_breakdown({"1": 60.0, "3": 30.0, "7": 10.0, "99": -0.0})},
        {"Type": "MorningStarDefault", "SalePosition": "S", "BreakdownValues": [{"Type": "1", "Value": 5.0}]},
    ],
    CountryExposure=[
        _breakdown({"USA": 75.0, "GBR": 25.0}, Type="Equity"),
        _breakdown({"GBR": 100.0}, Type="Bond"),
    ],
    GlobalStockSectorBreakdown=[_breakdown({"311": 50.0, "103": 50.0})],
    PortfolioHoldings=[
        {
            "SecurityName": "Apple Inc",
            "ISIN": "US0378331005",
            "Weighting": 3.0,
            "CountryId": "USA",
            "GlobalSectorId": "311",
        },
        {"SecurityName": "UK Gilt 4%", "ISIN": "GB00B0000001", "Weighting": 5.0, "CountryId": "GBR"},
        {"SecurityName": "Zero weight", "Weighting": 0},
    ],
    HoldingAggregates=[{"SalePosition": "N", "NumberOfHolding": 1234}],
)


def test_morningstar_snapshot_scales_sleeves_to_whole_fund():
    block = src.parse_morningstar_snapshot(MIXED_FUND, "0P0000TEST", TODAY)

    assert block["source"] == "morningstar"
    assert block["as_of"] == "2026-08-31"
    assert block["fetched"] == "2026-10-07"
    assert block["asset_mix"] == {"equity": 60.0, "bond": 30.0, "cash": 10.0}
    assert block["countries"] == {"United Kingdom": 45.0, "United States": 45.0, "Cash": 10.0}
    assert block["sectors"] == {
        "Information Technology": 30.0,
        "Financials": 30.0,
        "Fixed Income": 30.0,
        "Cash": 10.0,
    }
    assert block["holdings_count"] == 1234


def test_morningstar_holdings_sorted_with_labels():
    holdings = src.parse_morningstar_snapshot(MIXED_FUND, "X", TODAY)["top_holdings"]

    assert [h["name"] for h in holdings] == ["UK Gilt 4%", "Apple Inc"]
    assert holdings[1] == {
        "name": "Apple Inc",
        "isin": "US0378331005",
        "weight_pct": 3.0,
        "country": "United States",
        "sector": "Information Technology",
    }
    assert holdings[0]["sector"] is None


def test_morningstar_leverage_is_rescaled_to_100():
    snap = _snapshot(
        AssetAllocations=[{"Type": "MorningStarDefault", **_breakdown({"1": 103.0, "7": -3.0})}],
        CountryExposure=[_breakdown({"USA": 100.0}, Type="Equity")],
    )
    block = src.parse_morningstar_snapshot(snap, "X", TODAY)

    assert block["asset_mix"] == {"equity": 100.0}
    assert block["countries"] == {"United States": 100.0}
    # Equity with no sector breakdown is still accounted for.
    assert block["sectors"] == {"Other": 100.0}


def test_morningstar_without_breakdown_is_not_covered():
    assert src.parse_morningstar_snapshot(_snapshot(PortfolioHoldings=[]), "X", TODAY) is None
    assert src.parse_morningstar_snapshot({}, "X", TODAY) is None


JUSTETF_HTML = """
<html><body>
<div data-testid="etf-holdings_top-holdings_container"><table>
  <tr><td><a href="/en/stock-profiles/US67066G1040">NVIDIA Corp.</a></td><td>4.77%</td></tr>
  <tr><td>Unlisted thing</td><td>1.00%</td></tr>
</table></div>
<div data-testid="etf-holdings_countries_container"><table>
  <tr><td>United States</td><td>59.77%</td></tr><tr><td>Other</td><td>40.23%</td></tr>
</table></div>
<div data-testid="etf-holdings_sectors_container"><table>
  <tr><td>Technology</td><td>36.04%</td></tr><tr><td>Finance</td><td>18.63%</td></tr>
  <tr><td>Other</td><td>45.33%</td></tr>
</table></div>
<p>As of 31/08/2026</p>
</body></html>
"""


def test_justetf_profile_parsed_and_labels_normalised():
    block = src.parse_justetf_profile(JUSTETF_HTML, "IE00B3RBWM25", TODAY)

    assert block["source"] == "justetf"
    assert block["as_of"] == "2026-08-31"
    assert block["countries"] == {"United States": 59.77, "Other": 40.23}
    assert block["sectors"] == {"Other": 45.33, "Information Technology": 36.04, "Financials": 18.63}
    assert block["top_holdings"][0]["isin"] == "US67066G1040"
    assert block["top_holdings"][1]["isin"] is None


def test_justetf_page_without_breakdown_is_not_covered():
    assert src.parse_justetf_profile("<html></html>", "X", TODAY) is None


class _Resp:
    def __init__(self, status=200, text="", payload=None, redirect=False):
        self.status_code = status
        self.text = text
        self.is_redirect = redirect
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, params=None, timeout=None, allow_redirects=True):
        self.calls.append(url)
        for marker, resp in self.responses.items():
            if marker in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected url {url}")


def test_justetf_redirect_means_not_covered():
    session = _Session({"justetf": _Resp(302, redirect=True)})
    assert src.fetch_justetf("GB00BJLP1Y77", session, TODAY) is None


def test_morningstar_resolves_isin_then_reads_snapshot():
    session = _Session(
        {
            "screener": _Resp(
                payload={"rows": [{"SecId": "0PX", "isin": "IE00TEST0001"}, {"SecId": "0PY", "isin": "OTHER"}]}
            ),
            "security_details/0PX": _Resp(payload=[MIXED_FUND]),
        }
    )
    block = src.fetch_look_through("IE00TEST0001", session, TODAY)

    assert block["source_id"] == "0PX"
    assert not any("justetf" in c for c in session.calls)


def test_falls_back_to_justetf_when_morningstar_fails():
    session = _Session(
        {"screener": requests.ConnectionError("down"), "justetf": _Resp(text=JUSTETF_HTML)},
    )
    assert src.fetch_look_through("IE00B3RBWM25", session, TODAY)["source"] == "justetf"


def test_http_error_from_last_source_propagates():
    session = _Session({"screener": _Resp(payload={"rows": []}), "justetf": _Resp(403)})
    with pytest.raises(src.LookThroughFetchError):
        src.fetch_look_through("IE00B3RBWM25", session, TODAY)
