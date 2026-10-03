"""Guard the checked-in ``data/scaling_overrides.json`` against bad factors.

An override is the factor that turns a fetched LSE quote into GBP, so the
only meaningful values are 0.01 (quoted in pence) and 1 (quoted in pounds).
Any other factor is a typo that silently mis-scales every price for the
ticker -- e.g. ``"ADM": 0.1`` made Admiral Group (ADM.L) render 10x too
high, which surfaced as an apparent -90% move against paths that convert
via the instrument's GBX currency metadata instead (#8597).
"""

import json
from pathlib import Path

import pytest

from backend.utils import timeseries_helpers as th

OVERRIDES_PATH = Path(__file__).resolve().parents[1] / "data" / "scaling_overrides.json"
VALID_FACTORS = {0.01, 1.0}


def _load_overrides() -> dict:
    return json.loads(OVERRIDES_PATH.read_text())


def _entries() -> list[tuple[str, str, float]]:
    return [(ex, tkr, factor) for ex, table in _load_overrides().items() for tkr, factor in table.items()]


@pytest.mark.parametrize("exchange,ticker,factor", _entries())
def test_override_factor_is_a_currency_unit_factor(exchange, ticker, factor):
    assert float(factor) in VALID_FACTORS, (
        f"{ticker}.{exchange} override {factor} is not a pence (0.01) or pounds (1) factor. "
        "Any other value mis-scales every price for the ticker (see #8597). If a market "
        "genuinely needs another unit factor, add it to VALID_FACTORS with a comment saying why."
    )


def test_adm_override_scales_pence_to_pounds(monkeypatch):
    # With no configured roots, get_scaling_override falls back to
    # <repo>/data/scaling_overrides.json -- the checked-in file under test --
    # instead of whatever data_root/repo_root the local config points at.
    monkeypatch.setattr(th.config, "data_root", None, raising=False)
    monkeypatch.setattr(th.config, "repo_root", None, raising=False)
    assert th.get_scaling_override("ADM.L", "L", None) == pytest.approx(0.01)
    # Cached ADM.L closes are in pence (e.g. 3588 on 2026-10-02); the scaled
    # value must be the ~GBP 35.88 share price, not 358.80.
    assert 3588 * th.get_scaling_override("ADM", "L", None) == pytest.approx(35.88)
