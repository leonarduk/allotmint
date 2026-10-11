"""Declared dividend currency (#10742).

BCG.L trades in GBP but Yahoo stores its dividends as EUR amounts; total
return must convert them at the ex-date rate before reinvesting them.
"""

import logging
from datetime import date

import pandas as pd
import pytest

from backend.timeseries import dividend_currency as dc
from backend.timeseries import total_return as tr

BLOCK = {"currency": "EUR", "rationale": "Dividends declared in euro cents", "reviewed": "2026-10-11"}
EX_DATES = pd.to_datetime(["2025-09-11", "2025-12-11"])
EUR_GBP = {date(2025, 9, 10): 0.86, date(2025, 12, 10): 0.88}


@pytest.fixture
def declare(monkeypatch):
    """Instrument metadata for ``BCG.L`` and stored EUR->GBP rates (one day before each ex-date)."""
    metas: dict[str, dict] = {}
    monkeypatch.setattr(dc, "get_instrument_meta", lambda ticker: metas.get(ticker, {}))
    rates = pd.DataFrame({"Date": pd.to_datetime(list(EUR_GBP)), "Rate": list(EUR_GBP.values())})
    monkeypatch.setattr(dc, "_fx", lambda currency: rates if currency == "EUR" else rates.iloc[0:0])

    def _declare(currency="GBP", block=BLOCK, ticker="BCG.L"):
        metas[ticker] = {"currency": currency, **({"dividend_currency": block} if block is not None else {})}

    return _declare


def _dividends(values=(0.026832, 0.013292)):
    series = pd.Series(list(values), index=EX_DATES)
    series.attrs["confirmed_from"] = "2022-01-01"
    return series


def test_eur_dividends_convert_to_gbp_at_the_ex_date_rate(declare):
    declare()
    stored = _dividends()

    out = dc.convert_dividends(stored, "BCG", "L")

    assert out.tolist() == pytest.approx([0.026832 * 0.86, 0.013292 * 0.88])
    assert out.attrs == stored.attrs
    assert stored.tolist() == [0.026832, 0.013292]  # input not mutated


def test_pence_instrument_gets_pence(declare):
    declare(currency="GBX")
    out = dc.convert_dividends(_dividends(), "BCG", "L")
    assert out.tolist() == pytest.approx([0.026832 * 0.86 * 100, 0.013292 * 0.88 * 100])


def test_no_block_or_same_currency_returns_the_series_itself(declare):
    declare(block=None)
    stored = _dividends()
    assert dc.convert_dividends(stored, "BCG", "L") is stored
    declare(currency="EUR")
    assert dc.convert_dividends(stored, "BCG", "L") is stored


@pytest.mark.parametrize("currency", ["", "pounds", None])
def test_unknown_instrument_currency_refuses_to_pass_foreign_dividends_through(declare, currency):
    declare(currency=currency)
    assert dc.convert_dividends(_dividends(), "BCG", "L") is None


def test_missing_rate_refuses_to_guess(declare):
    declare()
    late = pd.Series([0.03], index=pd.to_datetime(["2026-09-10"]))  # > 5 days after the last stored rate
    assert dc.convert_dividends(late, "BCG", "L") is None


@pytest.mark.parametrize(
    "change, fragment",
    [
        ({"currency": "GBX"}, "currency"),
        ({"currency": "eur"}, "currency"),
        ({"currency": None}, "currency"),
        ({"rationale": " "}, "rationale"),
        ({"reviewed": "soon"}, "reviewed"),
    ],
)
def test_invalid_blocks_are_reported(change, fragment):
    problems = dc.validate_dividend_currency({"dividend_currency": {**BLOCK, **change}})
    assert len(problems) == 1 and fragment in problems[0]
    with pytest.raises(ValueError):
        dc.parse_dividend_currency({"dividend_currency": {**BLOCK, **change}})


def test_invalid_block_is_ignored_with_a_warning(declare, caplog):
    declare(block={**BLOCK, "reviewed": None})
    stored = _dividends()
    with caplog.at_level(logging.WARNING, logger=dc.__name__):
        assert dc.convert_dividends(stored, "BCG", "L") is stored
    assert "Ignoring invalid dividend_currency for BCG.L" in caplog.text


def test_total_return_reinvests_converted_dividends(declare):
    declare()
    restated = tr._dividends_for("BCG", "L", lambda _t, _e: _dividends())
    assert restated.tolist() == pytest.approx([0.026832 * 0.86, 0.013292 * 0.88])


def test_total_return_falls_back_to_price_basis_without_a_rate(declare):
    declare()
    late = pd.Series([0.03], index=pd.to_datetime(["2026-09-10"]))
    assert tr._dividends_for("BCG", "L", lambda _t, _e: late) is None
