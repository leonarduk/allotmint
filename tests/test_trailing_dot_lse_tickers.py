"""Padded LSE EPICs ("BP.", "AV.", "SN.") share one key with their ".L" listing (#8600)."""

import datetime as dt
import json
import logging

import pytest

from backend.common import holding_utils, portfolio_utils
from backend.common import instrument_api as ia
from backend.common.holdings_rebuild import rebuild_holdings_document, transaction_cost_hints
from backend.common.portfolio import fill_missing_costs
from backend.common.ticker_utils import canonical_ticker, split_ticker
from backend.utils import update_holdings_from_csv

# Captured at collection time: tests/test_accounts_api.py rebinds
# portfolio_utils.list_all_unique_tickers globally without restoring it.
_LIST_ALL_UNIQUE_TICKERS = portfolio_utils.list_all_unique_tickers


@pytest.mark.parametrize(
    ("ticker", "exchange", "expected"),
    [
        ("BP.", None, "BP.L"),
        ("bp.", None, "BP.L"),
        (" BP. ", None, "BP.L"),
        ("BP.L", None, "BP.L"),
        ("bp.l", None, "BP.L"),
        ("BP", "L", "BP.L"),
        ("BP", "l", "BP.L"),
        ("BP.", "N", "BP.L"),  # padded EPIC is always LSE
        ("PFE.N", "L", "PFE.N"),  # explicit suffix wins
        ("BP", None, "BP"),
        ("BP", "", "BP"),
        ("CASH.GBP", None, "CASH.GBP"),
        ("A.", None, "A.L"),  # one-character EPICs are padded too
        ("CASH.", None, "CASH"),  # 3+ characters: not a padded EPIC, so not LSE
        ("FOO.", None, "FOO"),
        ("FOO.", "N", "FOO.N"),  # stray dot dropped; the given exchange applies
        ("", None, ""),
        (None, "L", ""),
        (".", None, ""),
    ],
)
def test_canonical_ticker(ticker, exchange, expected):
    assert canonical_ticker(ticker, exchange) == expected


def test_split_ticker_never_returns_empty_exchange():
    assert split_ticker("BP.") == ("BP", "L")
    assert split_ticker("BP.L") == ("BP", "L")
    assert split_ticker("BP") == ("BP", None)
    assert split_ticker("BP", "") == ("BP", None)


@pytest.mark.parametrize("ticker", ["BP.", "bp.l", "BP", "CASH.", "CASH.GBP", "PFE.N", "A.", ""])
def test_canonical_ticker_is_idempotent(ticker):
    once = canonical_ticker(ticker)
    assert canonical_ticker(once) == once


@pytest.mark.parametrize("ticker", [".", "..", ".L", "   ", "", None])
def test_split_ticker_degenerate_input_has_no_exchange(ticker):
    assert split_ticker(ticker, "L") == ("", None)


def test_resolve_full_ticker_maps_padded_epic_to_lse(monkeypatch):
    monkeypatch.setattr(ia, "_TICKER_EXCHANGE_MAP", {})
    assert ia._resolve_full_ticker("BP.", {}) == ("BP", "L")
    assert ia._resolve_full_ticker("sn.", {}) == ("SN", "L")
    assert ia._resolve_full_ticker("BP.L", {}) == ("BP", "L")
    assert ia._resolve_full_ticker(".L", {}) is None


def test_load_latest_prices_reads_lse_series_for_padded_epic(monkeypatch):
    calls = []

    def fake_load(ticker, exchange, start_date, end_date):
        import pandas as pd

        calls.append((ticker, exchange))
        return pd.DataFrame({"Date": [dt.date(2026, 10, 1)], "Close_gbp": [5.5]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_load)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *a, **k: 1.0)

    result = holding_utils.load_latest_prices(["BP."])

    assert calls == [("BP", "L")]
    assert result == {"BP.L": 5.5}


def test_hargreaves_import_stores_padded_epic_as_lse(monkeypatch):
    def must_not_resolve(ticker):
        raise AssertionError("a padded EPIC already names its exchange")

    monkeypatch.setattr(update_holdings_from_csv, "resolve_instrument_ticker", must_not_resolve)
    assert update_holdings_from_csv._normalise_ticker("BP.", "hargreaves") == "BP.L"
    assert update_holdings_from_csv._normalise_ticker("av.", "hargreaves") == "AV.L"
    assert update_holdings_from_csv._normalise_ticker("BP.L", "hargreaves") == "BP.L"


def test_padded_and_suffixed_transactions_share_one_pool():
    txs = [
        {"date": "2025-05-09", "ticker": "BP.", "type": "BUY", "units": 842.0, "price_gbp": 3.5},
        {"date": "2025-06-01", "ticker": "BP.L", "type": "BUY", "units": 8.0, "price_gbp": 4.0},
    ]
    hints = transaction_cost_hints(txs)
    assert list(hints) == ["BP.L"]
    assert hints["BP.L"] == (842.0 * 3.5 + 8.0 * 4.0, None)


def test_rebuild_does_not_duplicate_a_padded_epic_holding():
    txs = [{"date": "2025-05-09", "ticker": "BP.", "type": "BUY", "units": 842.0, "price_gbp": 3.5}]
    existing = {"holdings": [{"ticker": "BP.", "units": 842.0, "cost_basis_gbp": 0.0}]}

    doc = rebuild_holdings_document({"transactions": txs}, "steve", "sipp", existing)

    assert [h["ticker"] for h in doc["holdings"]] == ["BP.L"]


def test_rebuild_collapsing_padded_and_suffixed_holdings_keeps_later_and_warns(caplog):
    txs = [{"date": "2025-05-09", "ticker": "BP.", "type": "BUY", "units": 842.0, "price_gbp": 3.5}]
    existing = {
        "holdings": [
            {"ticker": "BP.", "units": 842.0, "cost_basis_gbp": 0.0, "name": "older"},
            {"ticker": "BP.L", "units": 842.0, "cost_basis_gbp": 0.0, "name": "newer"},
        ]
    }

    with caplog.at_level(logging.WARNING, logger="backend.common.holdings_rebuild"):
        doc = rebuild_holdings_document({"transactions": txs}, "steve", "sipp", existing)

    assert [(h["ticker"], h.get("name")) for h in doc["holdings"]] == [("BP.L", "newer")]
    assert any("are both BP.L" in r.getMessage() for r in caplog.records)


def test_fill_missing_costs_matches_padded_epic_holding(tmp_path):
    owner_dir = tmp_path / "steve"
    owner_dir.mkdir()
    txs = [{"date": "2025-05-09", "ticker": "BP.", "type": "BUY", "units": 842.0, "price_gbp": 3.5}]
    (owner_dir / "SIPP_transactions.json").write_text(json.dumps({"transactions": txs}))
    holdings = [
        {"ticker": "BP.", "units": 842.0, "cost_basis_gbp": 0.0},
        {"ticker": "BP.L", "units": 842.0, "cost_basis_gbp": 0.0},
    ]

    fill_missing_costs("steve", "sipp", holdings, tmp_path)

    assert holdings[0]["cost_basis_gbp"] == 2947.0
    assert holdings[1]["cost_basis_gbp"] == 2947.0


def test_unique_tickers_collapse_padded_epic(monkeypatch):
    portfolios = [
        {
            "owner": "steve",
            "accounts": [
                {"account_type": "sipp", "holdings": [{"ticker": "BP."}, {"ticker": "bp.l"}, {"ticker": "AZN.L"}]}
            ],
        }
    ]
    monkeypatch.setattr(portfolio_utils, "list_portfolios", lambda: portfolios)
    monkeypatch.setattr(portfolio_utils, "list_virtual_portfolios", lambda: [])

    monkeypatch.setattr(portfolio_utils, "list_all_unique_tickers", _LIST_ALL_UNIQUE_TICKERS)

    assert sorted(portfolio_utils.list_all_unique_tickers()) == ["AZN.L", "BP.L"]


def test_enrich_holding_labels_and_prices_padded_epic_as_lse(monkeypatch):

    monkeypatch.setattr(
        portfolio_utils,
        "_PRICE_SNAPSHOT",
        {"BP.L": {"last_price": 5.5, "last_price_date": "2026-10-02", "is_stale": False}},
    )
    loads = []
    monkeypatch.setattr(
        holding_utils,
        "load_meta_timeseries_range",
        lambda ticker, exchange, **kwargs: loads.append((ticker, exchange)),
    )
    calc = holding_utils.PricingDateCalculator(today=dt.date(2026, 10, 3), reporting_date=dt.date(2026, 10, 2))

    out = holding_utils.enrich_holding(
        {"ticker": "BP.", "units": 10.0, "cost_basis_gbp": 40.0}, dt.date(2026, 10, 3), {}, {}, calc=calc
    )

    assert out["ticker"] == "BP.L"
    assert out["current_price_gbp"] == pytest.approx(5.5)
    assert out["market_value_gbp"] == pytest.approx(55.0)
    assert loads and all(load == ("BP", "L") for load in loads)
