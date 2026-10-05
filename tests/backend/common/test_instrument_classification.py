"""Tests for asset-class and fund-sector classification (#9196)."""

from __future__ import annotations

import json
import os

import pytest

from backend.common import instrument_classification as ic


def _meta(name, instrument_type=None, sector=None, **extra):
    meta = {"ticker": extra.pop("ticker", "TEST.L"), "name": name, "sector": sector}
    if instrument_type is not None:
        meta["instrumentType"] = instrument_type
    meta.update(extra)
    return meta


@pytest.mark.parametrize(
    "meta,asset_class,sector",
    [
        # ETFs and a trust filed under their issuer's sector (the issue's examples).
        (_meta("Vanguard FTSE All-World UCITS ETF (GBP)", "ETF", "Financials"), "equity", "Multi-sector"),
        (
            _meta("iShares IV plc Edge MSCI Europe Value Factor UCITS ETF", "ETF", "Financials"),
            "equity",
            "Multi-sector",
        ),
        (_meta("iShares VII plc MSCI UK Small CAP UCITS ETF", "ETF", "Financials"), "equity", "Multi-sector"),
        (
            _meta("Henderson Far East Income Ltd Ordinary NPV", "Investment Trust", "Financials"),
            "equity",
            "Multi-sector",
        ),
        (_meta("Ashoka India Equity Inv Trust Plc", "Investment Trust", "Miscellaneous"), "equity", "Multi-sector"),
        # A wrapper sector marks a fund and is replaced too.
        (_meta("Henderson Far East Income", None, "Investment Trust", asset_class="Equity"), "equity", "Multi-sector"),
        # Bond, cash, commodity and property products.
        (_meta("iShares IV plc GBP Ultrashort Bond UCITS ETF", "ETF", "Fixed Income"), "bond", None),
        (_meta("Goldman Sachs ETF ICAV Access UK Gilts 1-10 Years", "ETF", "Real Estate"), "bond", "Fixed Income"),
        (_meta("BioPharma Credit plc ORD USD0.01", "Investment Trust", "Financials"), "bond", "Fixed Income"),
        (_meta("TwentyFour Income Fund Ltd", "Investment Trust", "Fixed Income"), "bond", None),
        (_meta("Vanguard UK Gilt UCITS ETF", None, "Government Bond", asset_class="Bond"), "bond", None),
        (_meta("WisdomTree Physical Gold (GBP)", "Equity", "Materials"), "commodity", "Commodities"),
        (_meta("WisdomTree Energy", "ETF", "Commodities - Energy"), "commodity", None),
        (
            _meta("Schroder European Real Estate Investment Trust plc", "Investment Trust", "Real Estate"),
            "property",
            None,
        ),
        (_meta("Royal London Short Term Money Market Fund", "MUTUALFUND", None), "cash", "Cash"),
        (_meta("Vanguard LifeStrategy 60% Equity Fund", "MUTUALFUND", None), "multi-asset", "Multi-asset"),
        (_meta("Cash (GBP)", None, "", ticker="CASH.GBP"), "cash", "Cash"),
        # Gold *miners* are equities, and an equity sector on an equity fund is kept.
        (_meta("iShares V plc Gold Producers UCITS ETF", "ETF", "Materials"), "equity", None),
        (_meta("SPDR MSCI World Consumer Staples UCITS ETF", "ETF", "Consumer Staples"), "equity", None),
        # An equity fund mislabelled with an asset-class sector gets an exposure label.
        (_meta("iShares plc MSCI Brazil UCITS ETF (Dist)", "ETF", "Fixed Income"), "equity", "Multi-sector"),
        # Company shares keep their sector, even a financial one.
        (_meta("Admiral Group Ord GBP0.01", "Equity", "Financials"), "equity", None),
        (
            {"ticker": "AAL.L", "name": "ANGLO AMERICAN PLC", "instrument_type": "EQUITY", "sector": "Basic Materials"},
            "equity",
            None,
        ),
        (_meta("British Land Co plc Ordinary 25p", "Equity", "Real Estate Investment Trusts"), "equity", None),
    ],
)
def test_classify_instrument(meta, asset_class, sector) -> None:
    result = ic.classify_instrument(meta)
    assert result.get("asset_class") == asset_class
    assert result.get("sector") == sector


def test_yahoo_category_is_used_for_funds() -> None:
    meta = {"ticker": "X.L", "name": "Some Fund", "instrument_type": "MUTUALFUND", "category": "GBP Government Bond"}
    assert ic.classify_instrument(meta)["asset_class"] == "bond"


def test_stock_keyword_marks_equity_fund() -> None:
    meta = {"ticker": "X.L", "name": "Vanguard Total World Stock ETF", "sector": "Fixed Income"}
    assert ic.classify_instrument(meta) == {"asset_class": "equity", "sector": "Multi-sector"}


def test_bond_quote_type_without_keywords_is_bond() -> None:
    meta = {"ticker": "X.L", "name": "US 10Y Note", "instrument_type": "BOND"}
    assert ic.classify_instrument(meta)["asset_class"] == "bond"


@pytest.mark.parametrize("quote_type", ["INDEX", "CURRENCY", "CRYPTOCURRENCY", "FUTURE", "OPTION"])
def test_quote_types_outside_the_vocabulary_stay_unset(quote_type) -> None:
    meta = {"ticker": "X.L", "name": "Something", "instrument_type": quote_type}
    assert "asset_class" not in ic.classify_instrument(meta)


def test_unrecognised_override_is_logged_and_ignored(caplog) -> None:
    meta = _meta("Vanguard FTSE All-World UCITS ETF (GBP)", "ETF", "Financials")
    result = ic.classify_instrument(meta, {"asset_class": "Fund"})
    assert result["asset_class"] == "equity"
    assert "Ignoring unrecognised asset_class override" in caplog.text


def test_unknown_instrument_has_no_asset_class() -> None:
    assert ic.classify_instrument({"ticker": "AAA.L", "name": "AAA.L", "instrument_type": "NONE"}) == {}


def test_wrapper_values_are_not_asset_classes() -> None:
    meta = {"ticker": "X.L", "name": "X", "asset_class": "Fund"}
    assert ic.classify_instrument(meta) == {}


def test_override_wins() -> None:
    meta = _meta("iShares VI plc MSCI EUR HealthCare Sect UCITS ETF", "ETF", "Fixed Income")
    result = ic.classify_instrument(meta, {"sector": "Health Care"})
    assert result == {"asset_class": "equity", "sector": "Health Care"}

    result = ic.classify_instrument(meta, {"asset_class": "Bonds"})
    assert result == {"asset_class": "bond"}


def test_classification_is_idempotent() -> None:
    meta = _meta("Vanguard FTSE All-World UCITS ETF (GBP)", "ETF", "Financials")
    once = ic.apply_classification(meta)
    assert ic.classify_instrument(once) == {"asset_class": "equity"}


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Equity", "equity"),
        (" BONDS ", "bond"),
        ("Fixed Income", "bond"),
        ("Real Estate", "property"),
        ("Multi Asset", "multi-asset"),
        ("Fund", None),
        ("ETF", None),
        (None, None),
        (3, None),
    ],
)
def test_normalise_asset_class(value, expected) -> None:
    assert ic.normalise_asset_class(value) == expected


def test_load_overrides(tmp_path, caplog) -> None:
    path = tmp_path / "overrides.json"
    assert ic.load_classification_overrides(path) == {}

    path.write_text(
        json.dumps({"_comment": "ignored", "esih.l": {"sector": "Health Care"}, "BAD.L": "nope"}),
        encoding="utf-8",
    )
    assert ic.load_classification_overrides(path) == {"ESIH.L": {"sector": "Health Care"}}

    path.write_text("{not json", encoding="utf-8")
    assert ic.load_classification_overrides(path) == {}
    assert "Ignoring unreadable classification overrides" in caplog.text

    path.write_text("[]", encoding="utf-8")
    assert ic.load_classification_overrides(path) == {}


def test_overrides_path_uses_data_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ic.config, "data_root", tmp_path)
    assert ic.overrides_path() == tmp_path / ic.OVERRIDES_FILENAME


def test_overrides_path_falls_back_to_bundled_data(monkeypatch) -> None:
    monkeypatch.setattr(ic.config, "data_root", None)
    assert ic.overrides_path().parent.name == "data"


@pytest.mark.parametrize(
    "value,expected",
    [
        # Metadata persisted before #9196 used capitalised spellings.
        ("Equity", "equity"),
        ("Bond", "bond"),
        ("Commodity", "commodity"),
        (" EQUITY ", "equity"),
        ("equity", "equity"),
        # Labels outside the vocabulary are kept, not dropped.
        ("Fund", "Fund"),
        (" Index ", "Index"),
        ("", None),
        (None, None),
        (3, None),
    ],
)
def test_canonical_asset_class(value, expected) -> None:
    assert ic.canonical_asset_class(value) == expected


@pytest.mark.parametrize(
    "meta,expected",
    [
        ({"instrumentType": "ETF", "asset_class": "Equity"}, "ETF"),
        ({"instrument_type": "Investment Trust"}, "Investment Trust"),
        # Legacy and new asset classes resolve to the same instrument type.
        ({"asset_class": "Equity"}, "equity"),
        ({"asset_class": "equity"}, "equity"),
        ({"assetClass": "Bond"}, "bond"),
        ({"asset_class": "Fund"}, "Fund"),
        ({}, None),
    ],
)
def test_resolve_instrument_type(meta, expected) -> None:
    assert ic.resolve_instrument_type(meta) == expected


@pytest.mark.parametrize(
    "meta,expected",
    [
        # Un-backfilled fund records: issuer or wrapper sector -> exposure label.
        (_meta("Vanguard FTSE All-World UCITS ETF", "ETF", "Financials", asset_class="Equity"), "Multi-sector"),
        (_meta("iShares Core UK Gilts UCITS ETF", "ETF", "Financial Services"), "Fixed Income"),
        (_meta("Henderson Far East Income", None, "Investment Trust", asset_class="Equity"), "Multi-sector"),
        (_meta("WisdomTree Physical Gold", "ETC", "Materials"), "Commodities"),
        # An equity fund with a real sector keeps it.
        (_meta("SPDR MSCI World Consumer Staples UCITS ETF", "ETF", "Consumer Staples"), "Consumer Staples"),
        # Already backfilled: unchanged.
        (_meta("Vanguard FTSE All-World UCITS ETF", "ETF", "Multi-sector", asset_class="equity"), "Multi-sector"),
        # Company shares keep their sector, including Financials.
        (_meta("Lloyds Banking Group plc", "Equity", "Financials", asset_class="Equity"), "Financials"),
        (_meta("Lloyds Banking Group plc", "Equity", None), None),
    ],
)
def test_exposure_sector(meta, expected) -> None:
    assert ic.exposure_sector(meta) == expected


def test_exposure_sector_matches_backfill() -> None:
    """Read-time correction gives the same sector the backfill writes."""
    meta = _meta("iShares VII plc MSCI UK Small CAP UCITS ETF", "ETF", "Financials", asset_class="Fund")
    assert ic.exposure_sector(meta) == ic.classify_instrument(meta)["sector"]


def test_cached_overrides_reread_only_when_file_changes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ic.config, "data_root", tmp_path)
    path = tmp_path / ic.OVERRIDES_FILENAME
    assert ic.cached_classification_overrides() == {}

    path.write_text(json.dumps({"ESIH.L": {"sector": "Health Care"}}), encoding="utf-8")
    calls = []
    real_load = ic.load_classification_overrides
    monkeypatch.setattr(ic, "load_classification_overrides", lambda p: calls.append(p) or real_load(p))

    assert ic.cached_classification_overrides() == {"ESIH.L": {"sector": "Health Care"}}
    assert ic.cached_classification_overrides() == {"ESIH.L": {"sector": "Health Care"}}
    assert calls == [path]

    path.write_text(json.dumps({"ESIH.L": {"sector": "Health"}}), encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert ic.cached_classification_overrides() == {"ESIH.L": {"sector": "Health"}}
    assert len(calls) == 2

    ic.clear_overrides_cache()
    ic.cached_classification_overrides()
    assert len(calls) == 3
