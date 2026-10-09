"""Plan class -> long-history block table and the plan's real return series (#10484)."""

from __future__ import annotations

import pytest

from backend.common.investment_plan import PLAN_CLASSES
from backend.retirement.long_history import RETURN_BLOCKS
from backend.retirement.mapping import CLASS_BLOCKS, _year_ranges, blocks_used, data_notes, plan_real_returns

#: The documented table, pinned so any change to it is deliberate.
EXPECTED_TABLE = {
    "equity": ({"us_equity_gbp": 0.6, "ex_us_dev_equity_gbp": 0.4}, False, None),
    "small_cap_value": ({"us_small_value_gbp": 1.0}, False, "us_equity_gbp"),
    "long_gilts": ({"uk_govt_bond_10y": 1.0}, False, None),
    "intermediate_gilts": ({"uk_govt_bond_10y": 1.0}, True, None),
    "short_gilts": ({"uk_cash": 1.0}, False, None),
    "index_linked": ({"uk_govt_bond_10y": 1.0}, False, None),
    "overseas_government": ({"uk_govt_bond_10y": 1.0}, False, None),
    "corporate_bonds": ({"uk_govt_bond_10y": 1.0}, False, None),
    "gold": ({"gold_gbp": 1.0}, True, None),
    "other_commodities": ({"gold_gbp": 1.0}, False, None),
    "commodities": ({"gold_gbp": 1.0}, False, None),
    "cash": ({"uk_cash": 1.0}, True, None),
}


def test_table_matches_documented_mapping():
    actual = {key: (dict(m.blocks), m.exact, m.fallback) for key, m in CLASS_BLOCKS.items()}
    assert actual == EXPECTED_TABLE


def test_every_plan_class_is_mapped_to_known_blocks():
    assert set(CLASS_BLOCKS) == set(PLAN_CLASSES)
    for key, mapping in CLASS_BLOCKS.items():
        assert set(mapping.blocks) <= set(RETURN_BLOCKS), key
        assert sum(mapping.blocks.values()) == pytest.approx(1.0), key
        assert mapping.fallback is None or mapping.fallback in RETURN_BLOCKS
        assert mapping.note, key


def test_proxy_share_counts_inexact_classes(synthetic_history):
    returns = plan_real_returns({"cash": 50, "corporate_bonds": 30, "gold": 20}, synthetic_history)
    assert returns.proxy_share_pct == 30.0
    assert [p["class"] for p in returns.proxies] == ["corporate_bonds"]
    assert "no corporate bond series" in returns.proxies[0]["proxy"]


def test_real_return_is_cpi_deflated_and_rebalanced(synthetic_history):
    returns = plan_real_returns({"cash": 50, "intermediate_gilts": 50}, synthetic_history)
    # 0.5 * 4.04% + 0.5 * 2% = 3.02% nominal; (1.0302 / 1.02) - 1 = 1% real.
    assert returns.real_returns[2000] == pytest.approx(0.01)
    assert returns.proxy_share_pct == 0.0
    assert blocks_used({"cash": 0.5, "intermediate_gilts": 0.5}) == {"uk_cash": 0.5, "uk_govt_bond_10y": 0.5}


def test_blank_block_without_fallback_makes_year_unavailable(synthetic_history):
    returns = plan_real_returns({"cash": 50, "gold": 50}, synthetic_history)
    assert returns.real_returns[1990] is None and returns.real_returns[1991] is None
    assert returns.real_returns[1992] is not None
    assert returns.unavailable_reasons == {1990: ["gold_gbp"], 1991: ["gold_gbp"]}
    assert data_notes(returns) == ["No gold_gbp data for 1990-1991; windows touching those years are excluded."]


def test_blank_block_with_fallback_uses_named_proxy(synthetic_history):
    returns = plan_real_returns({"small_cap_value": 100}, synthetic_history)
    assert returns.fallback_years == {"small_cap_value": [1990, 1991, 1992, 1993, 1994]}
    # 1990 uses us_equity_gbp (+14.3%), not a 0% return.
    assert returns.real_returns[1990] == pytest.approx(1.143 / 1.02 - 1)
    assert data_notes(returns) == ["small_cap_value used us_equity_gbp for 1990-1994 (no small_cap_value data then)."]


def test_unknown_class_rejected(synthetic_history):
    with pytest.raises(ValueError, match="property"):
        plan_real_returns({"property": 100}, synthetic_history)


def test_weights_normalised(synthetic_history):
    a = plan_real_returns({"cash": 60, "intermediate_gilts": 40}, synthetic_history)
    b = plan_real_returns({"cash": 3, "intermediate_gilts": 2}, synthetic_history)
    assert a.real_returns == b.real_returns


def test_year_ranges():
    assert _year_ranges([]) == ""
    assert _year_ranges([1990]) == "1990"
    assert _year_ranges([1993, 1990, 1991]) == "1990-1991, 1993"
