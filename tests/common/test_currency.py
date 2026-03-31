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
    ],
)
def test_from_raw_variants(raw, canonical, display, is_pence, factor):
    normaliser = CurrencyNormaliser.from_raw(raw)

    assert normaliser.canonical == canonical
    assert normaliser.display_code == display
    assert normaliser.is_pence is is_pence
    assert normaliser.pence_factor == factor


def test_scale_dataframe_scales_ohlc_only_for_pence():
    normaliser = CurrencyNormaliser.from_raw("GBX")
    frame = pd.DataFrame({"Open": [100.0], "High": [200.0], "Close": [300.0], "Volume": [1000]})

    scaled = normaliser.scale_dataframe(frame)

    assert scaled["Open"].iloc[0] == pytest.approx(1.0)
    assert scaled["High"].iloc[0] == pytest.approx(2.0)
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
