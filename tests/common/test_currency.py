from __future__ import annotations

import pandas as pd
import pytest

from backend.common.currency import CurrencyNormaliser, extract_currency


@pytest.mark.parametrize(
    ("raw", "canonical", "display", "is_pence", "factor"),
    [
        ("GBX", "GBX", "GBP", True, 0.01),
        ("GBXP", "GBX", "GBP", True, 0.01),
        ("GBpx", "GBX", "GBP", True, 0.01),
        ("GBp", "GBX", "GBP", True, 0.01),
        ("GBP", "GBP", "GBP", False, 1.0),
        ("USD", "USD", "USD", False, 1.0),
        (None, "GBP", "GBP", False, 1.0),
        ("", "GBP", "GBP", False, 1.0),
        # "gbp" (all-lowercase) means GBP, NOT pence — critical distinction vs "GBp"
        ("gbp", "GBP", "GBP", False, 1.0),
    ],
)
def test_from_raw_variants(raw, canonical, display, is_pence, factor):
    normaliser = CurrencyNormaliser.from_raw(raw)

    assert normaliser.canonical == canonical
    assert normaliser.display_code == display
    assert normaliser.is_pence is is_pence
    assert normaliser.pence_factor == factor


def test_from_raw_gbp_lowercase_is_not_pence():
    """'gbp' (all-lowercase) is GBP, not pence. Only exact 'GBp' (Yahoo convention) is pence."""
    normaliser = CurrencyNormaliser.from_raw("gbp")
    assert normaliser.is_pence is False
    assert normaliser.canonical == "GBP"
    assert normaliser.display_code == "GBP"


def test_from_raw_GBp_is_pence():
    """Exact 'GBp' (Yahoo Finance convention) must be treated as pence."""
    normaliser = CurrencyNormaliser.from_raw("GBp")
    assert normaliser.is_pence is True
    assert normaliser.canonical == "GBX"
    assert normaliser.display_code == "GBP"


def test_scale_dataframe_scales_ohlc_only_for_pence():
    normaliser = CurrencyNormaliser.from_raw("GBX")
    frame = pd.DataFrame({"Open": [100.0], "High": [200.0], "Low": [150.0], "Close": [300.0], "Volume": [1000]})

    scaled = normaliser.scale_dataframe(frame)

    assert scaled["Open"].iloc[0] == pytest.approx(1.0)
    assert scaled["High"].iloc[0] == pytest.approx(2.0)
    assert scaled["Low"].iloc[0] == pytest.approx(1.5)
    assert scaled["Close"].iloc[0] == pytest.approx(3.0)
    assert scaled["Volume"].iloc[0] == pytest.approx(1000.0)


def test_to_gbp_uses_fx_for_non_gbp(monkeypatch):
    monkeypatch.setattr("backend.common.portfolio_utils._fx_to_base", lambda *_: 0.8)

    normaliser = CurrencyNormaliser.from_raw("USD")

    assert normaliser.to_gbp(100.0) == pytest.approx(80.0)


def test_extract_currency_from_nested_meta():
    normaliser = extract_currency({"quote": {"Currency": "GBpx"}})

    assert normaliser is not None
    assert normaliser.canonical == "GBX"


def test_to_gbp_pence_and_gbp_passthrough():
    assert CurrencyNormaliser.from_raw("GBX").to_gbp(250.0) == pytest.approx(2.5)
    assert CurrencyNormaliser.from_raw("GBP").to_gbp(250.0) == pytest.approx(250.0)


@pytest.mark.parametrize("bad_rate", [None, "oops", 0.0, -1.0, float("nan")])
def test_to_gbp_invalid_fx_rate_raises(monkeypatch, bad_rate):
    monkeypatch.setattr("backend.common.portfolio_utils._fx_to_base", lambda *_: bad_rate)

    with pytest.raises(ValueError):
        CurrencyNormaliser.from_raw("USD").to_gbp(100.0)


def test_extract_currency_returns_none_for_missing_meta():
    assert extract_currency(None) is None
    assert extract_currency({}) is None


def test_scale_dataframe_scales_volume_when_enabled():
    normaliser = CurrencyNormaliser.from_raw("GBX")
    frame = pd.DataFrame({"Open": [100.0], "Volume": [1000.0]})

    scaled = normaliser.scale_dataframe(frame, scale_volume=True)

    assert scaled["Open"].iloc[0] == pytest.approx(1.0)
    assert scaled["Volume"].iloc[0] == pytest.approx(10.0)


def test_scale_dataframe_is_noop_for_non_pence():
    normaliser = CurrencyNormaliser.from_raw("USD")
    frame = pd.DataFrame({"Open": [100.0], "Volume": [1000.0]})

    scaled = normaliser.scale_dataframe(frame, scale_volume=True)

    assert scaled.equals(frame)


@pytest.mark.parametrize("meta", [{"priceCurrency": "GBXP"}, {"currencyCode": "USD"}])
def test_extract_currency_from_top_level_keys(meta):
    normaliser = extract_currency(meta)

    assert normaliser is not None


def test_scale_dataframe_scales_case_insensitive_ohlc():
    """scale_dataframe must handle mixed-case column names (HIGH, low, Close, etc.).

    This confirms that the existing case-insensitive name_map in scale_dataframe
    works correctly for feeds that don't use title-case column names.
    """
    normaliser = CurrencyNormaliser.from_raw("GBX")
    frame = pd.DataFrame({"open": [100.0], "HIGH": [200.0], "low": [150.0], "Close": [300.0]})

    scaled = normaliser.scale_dataframe(frame)

    assert scaled["open"].iloc[0] == pytest.approx(1.0)
    assert scaled["HIGH"].iloc[0] == pytest.approx(2.0)
    assert scaled["low"].iloc[0] == pytest.approx(1.5)
    assert scaled["Close"].iloc[0] == pytest.approx(3.0)
