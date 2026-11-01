"""Tests for the goal completion projection (#7829)."""

from datetime import date

import pytest

from backend.common.goal_projection import (
    METHOD,
    MIN_HISTORY_DAYS,
    MIN_HISTORY_POINTS,
    project_completion,
)

TARGET_DATE = date(2030, 1, 1)


def test_no_history_is_insufficient():
    result = project_completion([], 1000.0, TARGET_DATE)
    assert result.status == "insufficient_history"
    assert result.points == 0
    assert result.projected_date is None


def test_single_point_is_never_extrapolated():
    result = project_completion([(date(2026, 1, 1), 100.0)], 1000.0, TARGET_DATE)
    assert result.status == "insufficient_history"
    assert result.projected_date is None


def test_same_day_entries_count_once():
    history = [(date(2026, 1, 1), 100.0), (date(2026, 1, 1), 150.0)]
    result = project_completion(history, 1000.0, TARGET_DATE)
    assert result.status == "insufficient_history"
    assert result.points == 1


def test_history_shorter_than_minimum_span_is_insufficient():
    history = [(date(2026, 1, 1), 100.0), (date(2026, 1, 20), 400.0)]
    result = project_completion(history, 1000.0, TARGET_DATE)
    assert result.status == "insufficient_history"
    assert result.points == 2
    assert result.history_start == date(2026, 1, 1)
    assert result.history_end == date(2026, 1, 20)


def test_linear_projection_from_first_to_latest_point():
    # 60 days, +300 => 5/day; 1500 remaining => 300 days after the latest point.
    history = [(date(2026, 3, 2), 500.0), (date(2026, 1, 1), 200.0), (date(2026, 2, 1), 999.0)]
    result = project_completion(history, 2000.0, TARGET_DATE)
    assert result.status == "projected"
    assert result.points == 3
    assert result.projected_date == date(2026, 12, 27)
    assert result.on_track is True
    assert result.monthly_rate == pytest.approx(152.19, abs=0.01)


def test_projection_after_target_date_is_not_on_track():
    history = [(date(2026, 1, 1), 0.0), (date(2026, 3, 2), 60.0)]  # 1/day
    result = project_completion(history, 10_000.0, date(2027, 1, 1))
    assert result.status == "projected"
    assert result.on_track is False


@pytest.mark.parametrize("latest", [200.0, 150.0])
def test_flat_or_falling_history_is_not_progressing(latest):
    history = [(date(2026, 1, 1), 200.0), (date(2026, 3, 2), latest)]
    result = project_completion(history, 1000.0, TARGET_DATE)
    assert result.status == "not_progressing"
    assert result.projected_date is None


def test_absurdly_slow_rate_does_not_overflow():
    history = [(date(2026, 1, 1), 0.0), (date(2026, 3, 2), 0.000001)]
    result = project_completion(history, 1e12, TARGET_DATE)
    assert result.status == "not_progressing"


def test_reached_target_reports_reached_even_with_one_point():
    result = project_completion([(date(2026, 1, 1), 1200.0)], 1000.0, TARGET_DATE)
    assert result.status == "reached"
    assert result.on_track is True


def test_to_dict_states_assumptions():
    history = [(date(2026, 1, 1), 200.0), (date(2026, 3, 2), 500.0)]
    data = project_completion(history, 2000.0, TARGET_DATE).to_dict()
    assert data["method"] == METHOD
    assert data["min_points"] == MIN_HISTORY_POINTS
    assert data["min_days"] == MIN_HISTORY_DAYS
    assert data["history_start"] == "2026-01-01"
    assert data["history_end"] == "2026-03-02"
    assert data["projected_date"] == "2026-12-27"
