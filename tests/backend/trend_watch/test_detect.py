"""The change-of-direction detector (#10476)."""

from __future__ import annotations

import pandas as pd

from backend.config import TrendWatchConfig
from backend.trend_watch import detect as d

from .fixtures import (
    FRESH_TURN_END,
    double_top,
    pence_cliff,
    rising_benchmark,
    rsi_dip,
)


def _fresh_turn(**kwargs) -> d.Detection:
    end = FRESH_TURN_END
    return d.detect(
        "TURN.L",
        double_top().iloc[:end],
        benchmark_levels=rising_benchmark().iloc[:end],
        benchmark_ticker="FTAL.L",
        return_basis="total",
        benchmark_return_basis="price",
        **kwargs,
    )


def test_fresh_death_cross_falling_200_day_and_new_rs_low_is_flagged():
    result = _fresh_turn()

    assert result.flagged
    assert {d.DEATH_CROSS, d.BELOW_FALLING_SMA200, d.RS_NEW_LOW} <= set(result.active)
    assert d.DEATH_CROSS in result.new
    assert result.values["sma50"] < result.values["sma200"]
    assert result.values["sma200_change"] < 0
    assert result.artefacts == []


def test_relative_figures_carry_their_return_basis():
    values = _fresh_turn().values

    assert values["return_basis"] == "total"
    assert values["benchmark"] == "FTAL.L"
    assert values["benchmark_return_basis"] == "price"
    assert values["excess_move"] == round(values["own_move"] - values["benchmark_move"], 4)


def test_rsi_dip_alone_is_not_flagged():
    result = d.detect("DIP.L", rsi_dip(), benchmark_levels=rising_benchmark())

    assert not result.flagged
    assert d.DEATH_CROSS not in result.active
    assert d.BELOW_FALLING_SMA200 not in result.active


def test_single_indicator_never_flags_even_when_new():
    cfg = TrendWatchConfig(min_signals=1, min_new_signals=1)

    # A config asking for one signal is still held to two: one reading is never enough.
    assert not d.is_flagged([d.DEATH_CROSS], [d.DEATH_CROSS], cfg)
    assert not d.is_flagged([d.MACD_NEGATIVE], [d.MACD_NEGATIVE], cfg)
    assert d.is_flagged([d.DEATH_CROSS, d.MACD_NEGATIVE], [d.DEATH_CROSS], cfg)
    # Relative strength and MACD both move on a short dip; without the price trend they do not flag.
    assert not d.is_flagged([d.RS_NEW_LOW, d.MACD_NEGATIVE], [d.RS_NEW_LOW], cfg)


def test_macd_or_swing_turning_does_not_make_a_flag_new():
    assert d.new_signals([d.MACD_NEGATIVE, d.LOWER_HIGHS_LOWS, d.DEATH_CROSS], {d.DEATH_CROSS}) == []
    assert d.new_signals([d.MACD_NEGATIVE, d.DEATH_CROSS], set()) == [d.DEATH_CROSS]


def test_long_standing_loser_is_not_reflagged_next_run():
    first = _fresh_turn()
    second = _fresh_turn(previous=first.state())

    assert first.flagged
    assert not second.flagged
    assert second.new == []
    assert second.values["new_relative_to"] == first.as_of


def test_signal_remembered_from_earlier_runs_is_not_new():
    first = _fresh_turn()
    earlier = {"as_of": "2025-01-01", "active": [], "recent": [[], [], [d.DEATH_CROSS]], "rs": None}

    assert d.DEATH_CROSS not in _fresh_turn(previous=earlier).new
    assert first.state()["recent"][0] == first.active


def test_short_history_is_skipped_with_a_reason():
    result = d.detect("NEW.L", double_top().iloc[:120])

    assert not result.flagged
    assert "200" in result.reason


def test_pence_cliff_is_reported_as_an_artefact():
    result = d.detect("JEGI.L", pence_cliff(), benchmark_levels=rising_benchmark())

    assert [step["kind"] for step in result.artefacts] == ["price_scale_step"]


def test_market_wide_compares_with_the_benchmark_move():
    closes = double_top().iloc[:FRESH_TURN_END]
    same = d.detect("BETA.L", closes, benchmark_levels=closes.copy(), benchmark_ticker="B.L")
    alone = _fresh_turn()

    assert d.market_wide(same) is True
    assert d.market_wide(alone) is False
    assert d.market_wide(d.detect("X.L", closes)) is None


def test_signal_frame_without_benchmark_never_reports_rs_low():
    frame = d.signal_frame(double_top())

    assert not frame[d.RS_NEW_LOW].any()
    assert d.signal_frame(pd.Series(dtype=float)).empty


def test_return_basis_is_never_left_blank():
    closes = double_top().iloc[:FRESH_TURN_END]
    bench = rising_benchmark().iloc[:FRESH_TURN_END]

    unstated = d.detect("X.L", closes, own_levels=closes, benchmark_levels=bench, benchmark_ticker="B.L").values
    traded = d.detect("X.L", closes, benchmark=bench, benchmark_ticker="B.L").values

    assert (unstated["return_basis"], unstated["benchmark_return_basis"]) == ("unstated", "unstated")
    assert (traded["return_basis"], traded["benchmark_return_basis"]) == ("price", "price")


def test_artefact_dates_are_iso_strings():
    step = d.find_artefacts(pence_cliff())[0]

    assert step["date"] == pence_cliff().index[-3].date().isoformat()
