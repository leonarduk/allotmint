"""Which data-quality issues send a flagged holding to "data problem, check first" (#10476)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.trend_watch import data_gate
from backend.trend_watch.detect import find_artefacts

from .fixtures import INDEX

SINCE = "2025-01-01"


def _issue(type_, severity, description="", **entity):
    return {
        "id": f"{type_}:X",
        "type": type_,
        "severity": severity,
        "entity": entity or {"ticker": "TURN", "exchange": "L"},
        "description": description,
    }


@pytest.mark.parametrize(
    "issue",
    [
        _issue("PRICE_SCALE_SUSPECT", "high", "Step on 2025-02-03"),
        _issue("ZERO_VOLUME_SPIKE", "medium", "Spike on 2025-03-10"),
        _issue("STALE_SERIES", "medium", "Last close 2025-02-20"),
        # No dates given: assume it may touch the window.
        _issue("MISSING_SERIES", "medium", "No cached series"),
        _issue("STALE_SERIES", "medium", "", holding="TURN.L", owner="alex", account="isa"),
    ],
)
def test_recent_high_or_medium_price_issue_blocks(issue):
    assert data_gate.blocking_issues("TURN.L", [issue], SINCE)[0]["type"] == issue["type"]


@pytest.mark.parametrize(
    "issue",
    [
        _issue("OUTLIERS", "low", "22 outlier point(s)"),
        _issue("LARGE_DAILY_MOVE", "low", "Move over 50% (latest 2025-02-01)"),
        _issue("ZERO_VOLUME_SPIKE", "medium", "Spike on 2014-01-07"),
        _issue("GAPS", "medium", "1 gap(s) covering 1 period(s)"),
        _issue("IMPLAUSIBLE_BOOK_COST", "high", "Book cost 100x value"),
        _issue("PRICE_SCALE_SUSPECT", "high", "Step on 2025-02-03", ticker="OTHER", exchange="L"),
    ],
)
def test_old_low_undated_gap_cost_or_other_ticker_issue_does_not_block(issue):
    assert data_gate.blocking_issues("TURN.L", [issue], SINCE) == []


def test_latest_date_reads_description_and_preview():
    issue = {"description": "from 2024-01-02", "preview": {"points": [{"date": "2025-05-06"}]}}

    assert data_gate.latest_date(issue) == "2025-05-06"
    assert data_gate.latest_date({"description": "none"}) is None


def test_missing_week_in_the_window_is_a_gap_artefact():
    closes = pd.Series(np.linspace(100, 120, 400), index=INDEX[:400]).drop(INDEX[380:388])

    gaps = [step for step in find_artefacts(closes) if step["kind"] == "gap"]
    reasons = data_gate.gate("TURN.L", [], gaps, SINCE)

    assert gaps and gaps[0]["missing_business_days"] >= 6
    assert reasons[0]["type"] == "GAPS"
    assert "missing" in reasons[0]["description"]
