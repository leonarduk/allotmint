"""Tests for equity/bond/commodity sub-class derivation (#9543, #9653)."""

import json

import pytest

from backend.common import instrument_classification
from backend.common.sub_asset_class import (
    SUB_ASSET_CLASS_PARENT,
    SUB_ASSET_CLASSES,
    derive_bond_sub_class,
    legacy_target_key,
    policy_targets,
    resolve_sub_asset_class,
)


@pytest.fixture(autouse=True)
def _no_overrides(tmp_path, monkeypatch):
    """Point the overrides file at an empty temp location for every test."""
    path = tmp_path / "instrument_classification_overrides.json"
    monkeypatch.setattr(instrument_classification, "overrides_path", lambda: path)
    instrument_classification.clear_overrides_cache()
    yield path
    instrument_classification.clear_overrides_cache()


def _facts(**facts):
    return {k: {"value": v} if isinstance(v, str) else v for k, v in facts.items()}


# Shapes copied from allotmint-data instrument metadata (fund_facts trimmed).
BONDS = [
    (
        "GLTL.L",
        "State Street SPDR Bloomberg 15+ Year Gilt UCITS ETF",
        _facts(effective_duration_years=15.04, maturity_band="15+ years"),
        "long_gilts",
    ),
    (
        "IGLT.L",
        "iShares Core UK Gilts UCITS ETF GBP (Dist)",
        _facts(effective_duration_years=6.99),
        "intermediate_gilts",
    ),
    (
        "GBPG.L",
        "Goldman Sachs ETF ICAV Access UK Gilts 1-10 Years UCITS ETF Class GBP Dis",
        _facts(maturity_band="1-10 years"),
        "intermediate_gilts",
    ),
    ("IGLS.L", "iShares UK Gilts 0-5yr UCITS ETF GBP (Dist)", _facts(effective_duration_years=2.17), "short_gilts"),
    (
        "ERNS.L",
        "iShares IV plc GBP Ultrashort Bond UCITS ETF GBP Dist",
        _facts(effective_duration_years=0.24, index="iBoxx GBP Liquid Investment Grade Ultrashort Index"),
        "short_gilts",
    ),
    (
        "INXG.L",
        "iShares Index-Linked Gilts UCITS ETF GBP (Dist)",
        _facts(effective_duration_years=12.66),
        "index_linked",
    ),
    (
        "GILG.L",
        "iShares III Plc Global Inflatin Linked Govt Bonds UCITS ETF GBP D",
        _facts(index="BBG World Government Inflation-Linked Bond Index (USD)"),
        "index_linked",
    ),
    ("SEGA.L", "iShares III plc Core Euro Government Bond UCITS ETF Dist", {}, "overseas_government"),
    ("ISXF.L", "iShares GBP Corporate Bond Ex-Financials UCITS ETF", {}, "corporate_bonds"),
    ("SLXX.L", "iShares Core Corp Bond UCITS ETF GBP (Dist)", {}, "corporate_bonds"),
    ("BPCR.L", "BioPharma Credit plc ORD USD0.01", {}, "corporate_bonds"),
    ("TFIF.L", "TwentyFour Income Fund Ltd Ordinary GBP 0.01", {}, "corporate_bonds"),
]


@pytest.mark.parametrize("ticker, name, facts, expected", BONDS)
def test_bond_sub_classes_derive_from_fund_facts_and_name(ticker, name, facts, expected):
    meta = {"ticker": ticker, "name": name, "fund_facts": facts}
    assert resolve_sub_asset_class(meta, "bond") == expected


# Names copied from allotmint-data instrument metadata.
@pytest.mark.parametrize(
    "ticker, name, expected",
    [
        ("PHGP.L", "WisdomTree Physical Gold (GBP)", "gold"),
        ("PHAU.L", "WisdomTree Physical Gold", "gold"),
        ("PHSP.L", "WisdomTree Physical Silver (GBP)", "other_commodities"),
        ("AIGE.L", "WisdomTree Energy *R", "other_commodities"),
    ],
)
def test_commodity_sub_classes(ticker, name, expected):
    assert resolve_sub_asset_class({"ticker": ticker, "name": name}, "commodity") == expected


@pytest.mark.parametrize(
    "duration, expected",
    [(2.99, "short_gilts"), (3.0, "intermediate_gilts"), (10.0, "intermediate_gilts"), (10.01, "long_gilts")],
)
def test_gilt_duration_band_edges(duration, expected):
    meta = {"name": "UK Gilts ETF", "fund_facts": {"effective_duration_years": duration}}
    assert derive_bond_sub_class(meta) == expected


def test_gilt_maturity_band_fact_used_without_duration():
    meta = {"name": "UK Gilts ETF", "fund_facts": {"maturity_band": {"value": "15+ years"}}}
    assert derive_bond_sub_class(meta) == "long_gilts"


def test_gilt_maturity_band_falls_back_to_name():
    assert derive_bond_sub_class({"name": "UK Gilts 0-5yr ETF"}) == "short_gilts"
    assert derive_bond_sub_class({"name": "15+ Year Gilt ETF"}) == "long_gilts"


def test_unknown_bond_has_no_sub_class():
    assert derive_bond_sub_class({"name": "Strategic Bond Fund"}) is None
    # A gilt fund with no duration, band or maturity in its name can't be banded.
    assert derive_bond_sub_class({"name": "iShares UK Gilts ETF", "fund_facts": {"maturity_band": "n/a"}}) is None


def test_non_splittable_classes_have_no_sub_class():
    assert resolve_sub_asset_class({"name": "UK Gilts 0-5yr"}, "property") is None
    assert resolve_sub_asset_class({"name": "UK Gilts 0-5yr"}, None) is None


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"name": "iShares S&P Small-Cap 600 Value"}, "small_cap_value"),
        ({"name": "SPDR MSCI USA Small Cap Value Weighted UCITS ETF"}, "small_cap_value"),
        ({"name": "Avantis Global SmallCap Value"}, "small_cap_value"),
        (
            {"name": "Some Fund", "fund_facts": {"index": {"value": "MSCI World Small Cap Value Weighted"}}},
            "small_cap_value",
        ),
        ({"name": "Vanguard FTSE All-World"}, "broad_equity"),
        ({"name": "iShares MSCI World Small Cap"}, "broad_equity"),
        ({"name": "Fidelity Value Fund"}, "broad_equity"),
    ],
)
def test_equity_sub_class(meta, expected):
    assert resolve_sub_asset_class(meta, "equity") == expected


def test_equity_override_wins(_no_overrides):
    _no_overrides.write_text(json.dumps({"ZPRV.L": {"sub_asset_class": "small_cap_value"}}))
    assert resolve_sub_asset_class({"ticker": "ZPRV.L", "name": "Some US ETF"}, "equity") == "small_cap_value"


def test_policy_targets_renames_equity_beside_an_equity_sub_class():
    assert policy_targets({"equity": 20, "small_cap_value": 20, "gold": 60}) == {
        "broad_equity": 20,
        "small_cap_value": 20,
        "gold": 60,
    }
    assert policy_targets({"equity": 40, "long_gilts": 60}) == {"equity": 40, "long_gilts": 60}


def test_policy_targets_renames_the_backtest_commodities_block_beside_gold():
    assert policy_targets({"equity": 85, "gold": 7.5, "commodities": 7.5}) == {
        "equity": 85,
        "gold": 7.5,
        "other_commodities": 7.5,
    }
    assert policy_targets({"equity": 80, "commodities": 20}) == {"equity": 80, "commodities": 20}


def test_policy_targets_sums_legacy_and_new_other_commodities():
    # Both keys name the same sleeve, so their weights add rather than one being dropped.
    assert policy_targets({"equity": 85, "gold": 5, "commodities": 5, "other_commodities": 5}) == {
        "equity": 85,
        "gold": 5,
        "other_commodities": 10,
    }


def test_legacy_target_key_needs_a_sibling_other_than_itself():
    assert legacy_target_key("commodities", frozenset({"commodities", "equity"})) == "commodities"
    assert legacy_target_key("commodities", frozenset({"commodities", "gold"})) == "other_commodities"


@pytest.mark.parametrize("override", ["commodities", "Commodities", "other_commodities"])
def test_legacy_commodities_override_is_the_other_commodities_sub_class(override, caplog):
    # An override is always a sub-class, so the pre-#9718 key needs no gold beside it.
    meta = {"ticker": "PHGP.L", "name": "WisdomTree Physical Gold", "sub_asset_class": override}
    assert resolve_sub_asset_class(meta, "commodity") == "other_commodities"
    assert "Ignoring sub_asset_class override" not in caplog.text


def test_legacy_commodities_override_in_the_overrides_file(_no_overrides):
    _no_overrides.write_text(json.dumps({"PHGP.L": {"sub_asset_class": "commodities"}}))
    meta = {"ticker": "PHGP.L", "name": "WisdomTree Physical Gold"}
    assert resolve_sub_asset_class(meta, "commodity") == "other_commodities"


def test_metadata_override_wins_over_derivation():
    meta = {"ticker": "PHSP.L", "name": "WisdomTree Physical Silver", "sub_asset_class": "Gold"}
    assert resolve_sub_asset_class(meta, "commodity") == "gold"


def test_overrides_file_wins_over_derivation(_no_overrides):
    _no_overrides.write_text(json.dumps({"tfif.l": {"sub_asset_class": "short_gilts"}}))
    meta = {"ticker": "TFIF.L", "name": "TwentyFour Income Fund"}
    assert resolve_sub_asset_class(meta, "bond") == "short_gilts"


def test_override_from_another_class_is_ignored(caplog):
    meta = {"ticker": "PHGP.L", "name": "WisdomTree Physical Gold", "sub_asset_class": "long_gilts"}
    assert resolve_sub_asset_class(meta, "commodity") == "gold"
    assert "Ignoring sub_asset_class override" in caplog.text


def test_parent_map_covers_every_sub_class():
    assert set(SUB_ASSET_CLASS_PARENT) == {s for subs in SUB_ASSET_CLASSES.values() for s in subs}
