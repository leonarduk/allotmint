"""Pin the committed ``data/scaling_overrides.json`` so it can't silently drift (#7787).

``get_scaling_override`` resolves an LSE ticker's GBP factor from the override
table first, then from ``currency`` metadata. These tests read the real table
(not a fixture) and cover one ticker of each kind:

- GBP-tagged but pence-quoted: needs an explicit 0.01 override.
- GBX-tagged: 0.01 comes from metadata, no override needed.
- Genuinely GBP-quoted: factor stays 1.0.
"""

import json
from pathlib import Path

import pytest

from backend.utils import timeseries_helpers as th

REPO_ROOT = Path(__file__).resolve().parents[1]
OVERRIDES_PATH = REPO_ROOT / "data" / "scaling_overrides.json"

# LSE stocks/trusts whose metadata says GBP but which quote in pence (#7787).
# ADM.L's 0.1 -> 0.01 correction landed in #8598; it is listed here too so all
# four #7787 tickers are pinned in one place.
PENCE_QUOTED_GBP_TAGGED = ["ADM", "AV", "CLIG", "HICL"]

# GBP-tagged LSE ETFs that really are quoted in pounds; a blanket exchange-level
# 0.01 would wrongly divide all of these by 100 (#7787).
GENUINELY_GBP_ETFS = [
    "ERNS",
    "GBPG",
    "SEGA",
    "VHYL",
    "VWRL",
    "ISXF",
    "WCOS",
    "GILG",
    "AIGE",
    "ESIH",
]


@pytest.fixture
def real_overrides(monkeypatch):
    monkeypatch.setattr(th.config, "repo_root", REPO_ROOT)


def _stub_currency(monkeypatch, currency):
    from backend.common import instruments, portfolio_utils

    monkeypatch.setattr(instruments, "get_instrument_meta", lambda ticker: {"currency": currency})
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda ticker: {"currency": currency})


@pytest.mark.parametrize("base", PENCE_QUOTED_GBP_TAGGED)
def test_pence_quoted_gbp_tagged_tickers_scale_to_pounds(real_overrides, monkeypatch, base):
    # Metadata says GBP, so only the override table can supply the pence factor.
    _stub_currency(monkeypatch, "GBP")

    assert th.get_scaling_override(f"{base}.L", "L", None) == pytest.approx(0.01)


def test_gbx_tagged_ticker_scales_from_metadata(real_overrides, monkeypatch):
    _stub_currency(monkeypatch, "GBX")

    assert th.get_scaling_override("ULVR.L", "L", None) == pytest.approx(0.01)


@pytest.mark.parametrize("base", GENUINELY_GBP_ETFS)
def test_genuinely_gbp_etfs_are_not_rescaled(real_overrides, monkeypatch, base):
    _stub_currency(monkeypatch, "GBP")

    assert th.get_scaling_override(f"{base}.L", "L", None) == pytest.approx(1.0)


def test_override_table_has_no_exchange_wide_wildcard():
    overrides = json.loads(OVERRIDES_PATH.read_text())

    assert "*" not in overrides.get("L", {})
    assert "*" not in overrides
