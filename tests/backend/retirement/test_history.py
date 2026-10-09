"""history.attribute_change with a stub compute (#10484): the parts always add up to the change."""

from __future__ import annotations

import pytest

from backend.retirement import history

PREVIOUS = {
    "run_date": "2030-01-15",
    "inputs": {"pot_gbp": 100.0, "retirement_age": 60},
    "headline": {"income_gbp": 10.0},
}


def _compute(inputs):
    # Income is 10% of the pot, minus 1 for each year of retirement age above 60.
    return inputs["pot_gbp"] * 0.1 - (inputs["retirement_age"] - 60)


def test_contribution_only_change_is_all_contributions():
    current = {"pot_gbp": 150.0, "retirement_age": 60}
    change = history.attribute_change(PREVIOUS, current, _compute(current), flows_gbp=50.0, compute=_compute)
    assert change["change_gbp"] == 5.0
    assert change["parts_gbp"] == {"data_revision": 0.0, "contributions": 5.0, "markets": 0.0, "assumptions": 0.0}


def test_mixed_change_splits_and_sums_exactly():
    current = {"pot_gbp": 130.0, "retirement_age": 62}  # +20 paid in, +10 markets, retire 2 years later
    change = history.attribute_change(PREVIOUS, current, _compute(current), flows_gbp=20.0, compute=_compute)
    assert change["parts_gbp"] == {"data_revision": 0.0, "contributions": 2.0, "markets": 1.0, "assumptions": -2.0}
    assert sum(change["parts_gbp"].values()) == pytest.approx(change["change_gbp"])


def test_data_revision_when_stored_figure_differs_from_recompute():
    previous = {**PREVIOUS, "headline": {"income_gbp": 9.5}}
    current = {"pot_gbp": 100.0, "retirement_age": 60}
    change = history.attribute_change(previous, current, _compute(current), flows_gbp=0.0, compute=_compute)
    assert change["parts_gbp"]["data_revision"] == 0.5
    assert change["change_gbp"] == 0.5


def test_rounded_parts_add_up_to_rounded_change():
    current = {"pot_gbp": 100.0 + 1 / 3, "retirement_age": 60}
    change = history.attribute_change(PREVIOUS, current, _compute(current), flows_gbp=1 / 7, compute=_compute)
    assert round(sum(change["parts_gbp"].values()), 2) == change["change_gbp"]
