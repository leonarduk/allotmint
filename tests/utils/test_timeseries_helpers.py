import builtins
import datetime as dt
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd

import backend.utils.timeseries_helpers as th


def test_apply_scaling_basic():
    df = pd.DataFrame({"Open": [1], "Close": [2], "Volume": [3]})
    scaled = th.apply_scaling(df, 2, scale_volume=True)
    assert list(scaled["Open"]) == [2]
    assert list(scaled["Close"]) == [4]
    assert list(scaled["Volume"]) == [6]


def test_apply_scaling_no_scale_returns_same_object():
    df = pd.DataFrame({"Open": [1]})
    same = th.apply_scaling(df, 1)
    assert same is df


def test_get_scaling_override_requested():
    assert th.get_scaling_override("T", "L", 3.0) == 3.0


def test_get_scaling_override_from_json():
    assert th.get_scaling_override("GAMA", "L", None) == 0.01
    assert th.get_scaling_override("ADM", "L", None) == 0.1


def test_get_scaling_override_from_json_lse_pence_tickers():
    # Regression test for #6845: GSK.L and HFEL.L both fetch as raw pence
    # (e.g. GSK.L returning "1888.0" for a real price of ~GBP18.88) but their
    # instrument metadata's `currency` is "GBP", not a pence code, so nothing
    # else in the pipeline would catch this without an explicit override.
    assert th.get_scaling_override("GSK", "L", None) == 0.01
    assert th.get_scaling_override("HFEL", "L", None) == 0.01


def test_get_scaling_override_missing_file(monkeypatch):
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    assert th.get_scaling_override("T", "X", None) == 1.0


def test_get_scaling_override_nested_currency(monkeypatch):
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta",
        lambda symbol: {"price": {"currency": "GBp"}},
    )

    assert th.get_scaling_override("TEST", "L", None) == 0.01


def test_get_scaling_override_security_meta_fallback(monkeypatch):
    monkeypatch.setattr(
        "backend.common.instruments.get_instrument_meta",
        lambda symbol: {},
    )
    monkeypatch.setattr(
        "backend.common.portfolio_utils.get_security_meta",
        lambda symbol: {"currency": "USD"},
    )

    assert th.get_scaling_override("TEST", "NYSE", None) == 1.0


def test_handle_timeseries_response_variants(monkeypatch):
    df = pd.DataFrame({"Date": ["2024-01-01"], "Open": [1], "Close": [1], "High": [1], "Low": [1], "Volume": [0]})

    # JSON
    resp = th.handle_timeseries_response(df, "json", "t", "s", {"meta": 1})
    body = json.loads(resp.body)
    assert body["meta"] == 1
    assert body["prices"][0]["Open"] == 1

    # CSV
    resp_csv = th.handle_timeseries_response(df, "csv", "t", "s")
    assert resp_csv.media_type == "text/csv"
    assert "Open" in resp_csv.body.decode()

    # HTML branch
    monkeypatch.setattr(th, "render_timeseries_html", lambda df, t, s: "HTML")
    resp_html = th.handle_timeseries_response(df, "html", "t", "s")
    assert resp_html == "HTML"

    # Empty DataFrame -> 404
    resp_empty = th.handle_timeseries_response(pd.DataFrame(), "json", "t", "s")
    assert resp_empty.status_code == 404

    # JSON without metadata
    resp_plain = th.handle_timeseries_response(df, "json", "t", "s")
    body_plain = json.loads(resp_plain.body)
    assert body_plain[0]["Open"] == 1


def test_get_scaling_override_bad_json(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "scaling_overrides.json").write_text("not json")
    monkeypatch.setattr(th, "config", SimpleNamespace(repo_root=tmp_path))
    assert th.get_scaling_override("T", "X", None) == 1.0


def test_get_scaling_override_invalid_value(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "scaling_overrides.json").write_text('{"*": {"*": "bad"}}')
    monkeypatch.setattr(th, "config", SimpleNamespace(repo_root=tmp_path))
    assert th.get_scaling_override("T", "X", None) == 1.0


def test_nearest_weekday():
    sat = dt.date(2024, 1, 6)
    sun = dt.date(2024, 1, 7)
    assert th._nearest_weekday(sat, True) == dt.date(2024, 1, 8)
    assert th._nearest_weekday(sat, False) == dt.date(2024, 1, 5)
    assert th._nearest_weekday(sun, False) == dt.date(2024, 1, 5)


def test_is_isin():
    assert th._is_isin("US0378331005")
    assert not th._is_isin("PFE")


# ── resolve_date_range ──────────────────────────────────────────────────────


class TestResolveDateRange:
    """Tests for the resolve_date_range service helper."""

    def test_positive_days_sets_start_relative_to_today(self, monkeypatch):
        today = dt.date(2024, 6, 15)
        monkeypatch.setattr(dt, "date", _make_frozen_date(today))
        start, end = th.resolve_date_range(30)
        assert start == dt.date(2024, 5, 16)
        assert end == dt.date(2024, 6, 14)

    def test_zero_days_returns_epoch_start(self, monkeypatch):
        today = dt.date(2024, 6, 15)
        monkeypatch.setattr(dt, "date", _make_frozen_date(today))
        start, end = th.resolve_date_range(0)
        assert start == dt.date(1900, 1, 1)
        assert end == dt.date(2024, 6, 14)

    def test_negative_days_returns_epoch_start(self, monkeypatch):
        today = dt.date(2024, 6, 15)
        monkeypatch.setattr(dt, "date", _make_frozen_date(today))
        start, end = th.resolve_date_range(-1)
        assert start == dt.date(1900, 1, 1)

    def test_explicit_start_date_overrides_days(self, monkeypatch):
        today = dt.date(2024, 6, 15)
        monkeypatch.setattr(dt, "date", _make_frozen_date(today))
        explicit_start = dt.date(2024, 1, 1)
        start, end = th.resolve_date_range(365, start_date=explicit_start)
        assert start == explicit_start
        assert end == dt.date(2024, 6, 14)

    def test_explicit_end_date_overrides_yesterday(self, monkeypatch):
        today = dt.date(2024, 6, 15)
        monkeypatch.setattr(dt, "date", _make_frozen_date(today))
        explicit_end = dt.date(2024, 3, 31)
        start, end = th.resolve_date_range(90, end_date=explicit_end)
        assert end == explicit_end

    def test_both_explicit_dates_ignore_days_entirely(self):
        explicit_start = dt.date(2023, 1, 1)
        explicit_end = dt.date(2023, 12, 31)
        start, end = th.resolve_date_range(999, start_date=explicit_start, end_date=explicit_end)
        assert start == explicit_start
        assert end == explicit_end

    def test_returns_tuple_of_date_objects(self):
        start, end = th.resolve_date_range(10)
        assert isinstance(start, dt.date)
        assert isinstance(end, dt.date)


class TestApplyDateRange:
    BASE = dt.date(2024, 1, 1)
    MID = dt.date(2024, 6, 15)
    END = dt.date(2024, 12, 31)

    def _df(self, dates: list[dt.date], *, as_datetime: bool = False) -> pd.DataFrame:
        if as_datetime:
            col = pd.to_datetime([dt.datetime(d.year, d.month, d.day) for d in dates])
        else:
            col = dates
        return pd.DataFrame({"Date": col, "Close": range(len(dates))})

    def test_start_date_only(self):
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, start_date=self.MID)
        assert list(result["Date"].dt.date) == [self.MID, self.END]

    def test_end_date_only(self):
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, end_date=self.MID)
        assert list(result["Date"].dt.date) == [self.BASE, self.MID]

    def test_both_bounds(self):
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.MID)
        assert list(result["Date"].dt.date) == [self.BASE, self.MID]

    def test_neither_bound_noop(self):
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df)
        assert len(result) == 3

    def test_boundary_dates_inclusive(self):
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.END)
        assert len(result) == 3

    def test_plain_date_column(self):
        # Date column stored as object dtype (plain date objects, no .dt accessor)
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=False)
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.MID)
        assert list(result["Date"]) == [self.BASE, self.MID]

    def test_empty_dataframe_returns_empty(self):
        df = pd.DataFrame({"Date": pd.Series([], dtype="datetime64[ns]"), "Close": []})
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.END)
        assert result.empty

    def test_missing_date_column_returns_df_unchanged(self):
        df = pd.DataFrame({"Close": [1, 2, 3]})
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.END)
        assert list(result["Close"]) == [1, 2, 3]

    def test_missing_date_column_not_mutated(self):
        df = pd.DataFrame({"Close": [1, 2, 3]})
        result = th.apply_date_range(df, start_date=self.BASE)
        result["Close"] = 99  # mutate the returned frame
        assert list(df["Close"]) == [1, 2, 3]  # original must be untouched

    def test_nat_rows_are_dropped(self):
        # datetime64 column: NaT is silently excluded regardless of bounds
        col = pd.to_datetime([self.BASE, None, self.END])
        df = pd.DataFrame({"Date": col, "Close": [1, 2, 3]})
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.END)
        assert len(result) == 2
        assert list(result["Close"]) == [1, 3]

    def test_none_rows_dropped_plain_date_column(self):
        # Object-dtype column: None must not reach the >= comparison (TypeError in Python >= 3.10)
        col = [self.BASE, None, self.END]
        df = pd.DataFrame({"Date": col, "Close": [1, 2, 3]})
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.END)
        assert len(result) == 2
        assert list(result["Close"]) == [1, 3]

    def test_index_is_reset(self):
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, start_date=self.MID, end_date=self.END)
        assert list(result.index) == [0, 1]

    def test_datetime64_dtype_preserved_in_output(self):
        # _ensure_schema handles either dtype, but confirm apply_date_range does not
        # silently convert the returned Date column away from datetime64.
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.MID)
        assert pd.api.types.is_datetime64_any_dtype(result["Date"])

    def test_plain_date_dtype_preserved_in_output(self):
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=False)
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.MID)
        assert result["Date"].dtype == object

    def test_original_frame_not_mutated(self):
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        original_index = list(df.index)
        th.apply_date_range(df, start_date=self.MID, end_date=self.END)
        assert list(df.index) == original_index
        assert len(df) == 3

    # ── #8127: searchsorted fast path (sorted, non-null datetime64 column) ──

    def test_fast_path_empty_range_both_bounds_after_data(self):
        # Range entirely after the last row: empty result, not an off-by-one.
        dates = [self.BASE, self.MID]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, start_date=self.END, end_date=self.END)
        assert result.empty

    def test_fast_path_empty_range_both_bounds_before_data(self):
        # Range entirely before the first row.
        dates = [self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.BASE)
        assert result.empty

    def test_fast_path_start_after_end_returns_empty(self):
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, start_date=self.END, end_date=self.BASE)
        assert result.empty

    def test_fast_path_duplicate_dates_all_included(self):
        # searchsorted with duplicate boundary values must not drop or
        # double-count rows sharing the same Date.
        dates = [self.BASE, self.MID, self.MID, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        result = th.apply_date_range(df, start_date=self.MID, end_date=self.MID)
        assert len(result) == 3

    def test_fast_path_time_of_day_component_end_of_day_inclusive(self):
        # A Date column that carries a nonzero time-of-day must still treat
        # end_date as inclusive of the whole calendar day (half-open upper
        # bound), not just midnight.
        col = pd.to_datetime(
            [
                dt.datetime.combine(self.BASE, dt.time(0, 0)),
                dt.datetime.combine(self.MID, dt.time(9, 30)),
                dt.datetime.combine(self.MID, dt.time(23, 59)),
                dt.datetime.combine(self.END, dt.time(0, 0)),
            ]
        )
        df = pd.DataFrame({"Date": col, "Close": range(4)})
        assert df["Date"].is_monotonic_increasing
        result = th.apply_date_range(df, start_date=self.MID, end_date=self.MID)
        assert len(result) == 2

    def test_unsorted_datetime_column_falls_back_to_scan(self):
        # Deliberately out-of-order Date column: the fast path must not be
        # taken, and the result must still be correct (same as the sorted
        # equivalent, modulo row order).
        dates = [self.MID, self.BASE, self.END]
        df = self._df(dates, as_datetime=True)
        assert not df["Date"].is_monotonic_increasing
        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.MID)
        assert sorted(result["Date"].dt.date) == [self.BASE, self.MID]

    def test_sorted_and_unsorted_paths_agree(self):
        # Cross-check: filtering a sorted frame and its shuffled equivalent
        # (row order aside) must produce the same set of rows.
        dates = [self.BASE, self.MID, self.END]
        sorted_df = self._df(dates, as_datetime=True)
        shuffled_df = self._df([self.MID, self.END, self.BASE], as_datetime=True)
        sorted_result = th.apply_date_range(sorted_df, start_date=self.BASE, end_date=self.MID)
        shuffled_result = th.apply_date_range(shuffled_df, start_date=self.BASE, end_date=self.MID)
        assert sorted(sorted_result["Date"].dt.date) == sorted(shuffled_result["Date"].dt.date)

    def test_fast_path_matches_scan_path_via_monkeypatch(self, monkeypatch):
        # Directly compares the sorted (fast) path's output against the
        # scan-based path on the *same* sorted, non-null data, by forcing the
        # guard's `is_monotonic_increasing` check to report False for the
        # second call -- pinning down that the optimisation is
        # behaviour-preserving rather than merely "looks right" on disjoint
        # fixtures.
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        fast_result = th.apply_date_range(df, start_date=self.BASE, end_date=self.MID)

        real_is_monotonic_increasing = pd.Series.is_monotonic_increasing

        def _fake_is_monotonic_increasing(self):
            if self.name == "Date":
                return False
            return real_is_monotonic_increasing.__get__(self)

        monkeypatch.setattr(
            pd.Series,
            "is_monotonic_increasing",
            property(_fake_is_monotonic_increasing),
        )
        scan_result = th.apply_date_range(df, start_date=self.BASE, end_date=self.MID)

        assert list(fast_result["Date"].dt.date) == list(scan_result["Date"].dt.date)
        assert list(fast_result["Close"]) == list(scan_result["Close"])

    def test_fast_and_scan_paths_agree_for_datetime_bounds_with_time_component(self, monkeypatch):
        # A caller passing datetime.datetime bounds with a nonzero time (not
        # just datetime.date) must get the same rows on both paths. Before
        # the bound-normalisation fix, the fast path's pd.Timestamp(start_date)
        # kept the time component and searchsorted against it directly, which
        # could exclude same-day rows the date-truncating scan path includes.
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        start_with_time = dt.datetime.combine(self.BASE, dt.time(15, 0))
        end_with_time = dt.datetime.combine(self.MID, dt.time(9, 0))

        fast_result = th.apply_date_range(df, start_date=start_with_time, end_date=end_with_time)

        real_is_monotonic_increasing = pd.Series.is_monotonic_increasing

        def _fake_is_monotonic_increasing(self):
            if self.name == "Date":
                return False
            return real_is_monotonic_increasing.__get__(self)

        monkeypatch.setattr(
            pd.Series,
            "is_monotonic_increasing",
            property(_fake_is_monotonic_increasing),
        )
        scan_result = th.apply_date_range(df, start_date=start_with_time, end_date=end_with_time)

        assert list(fast_result["Date"].dt.date) == list(scan_result["Date"].dt.date)
        # Both bounds fall on days present in the data (BASE, MID); truncating
        # the time component must still include both of those calendar days.
        assert list(fast_result["Date"].dt.date) == [self.BASE, self.MID]

    def test_np_datetime64_bounds_with_time_component_truncate_like_datetime(self):
        # #8131 review: hasattr(x, "date") skips np.datetime64 (it has no
        # .date() method), so a np.datetime64 bound with a nonzero time could
        # retain that time on the fast path and exclude same-day rows.
        # pd.Timestamp(x).normalize() handles np.datetime64 identically to
        # datetime.datetime/pd.Timestamp.
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)
        start = np.datetime64("2024-01-01T15:00:00")
        end = np.datetime64("2024-06-15T09:00:00")

        result = th.apply_date_range(df, start_date=start, end_date=end)

        assert list(result["Date"].dt.date) == [self.BASE, self.MID]

    def test_tz_aware_column_uses_local_calendar_day_not_utc_day(self):
        # #8131 review (fair): the previous tz-aware test used UTC, where the
        # local and UTC calendar day are identical -- it would pass even if
        # the fallback silently used the wrong day. Asia/Tokyo is UTC+9, so
        # local midnight is the *previous* UTC calendar day -- a real
        # boundary crossing. The scan path's `.dt.date` reports the column's
        # own local date, which is what a caller comparing against a plain
        # (timezone-less) `datetime.date` bound expects.
        col = pd.Series(pd.to_datetime([self.BASE, self.MID, self.END])).dt.tz_localize("Asia/Tokyo")
        df = pd.DataFrame({"Date": col, "Close": range(3)})
        # Sanity check the fixture actually crosses a UTC day boundary --
        # otherwise this test would be as vacuous as the one it replaces.
        assert col.dt.tz_convert("UTC").dt.date.tolist() != col.dt.date.tolist()

        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.MID)

        assert list(result["Date"].dt.date) == [self.BASE, self.MID]

    def test_open_ended_ranges_on_fast_path(self):
        # #8131 review: start_date=None/end_date=None on the sorted-datetime64
        # fast path weren't directly pinned (only exercised as a side effect
        # of other tests).
        dates = [self.BASE, self.MID, self.END]
        df = self._df(dates, as_datetime=True)

        assert list(th.apply_date_range(df, start_date=self.MID)["Date"].dt.date) == [self.MID, self.END]
        assert list(th.apply_date_range(df, end_date=self.MID)["Date"].dt.date) == [self.BASE, self.MID]
        assert list(th.apply_date_range(df)["Date"].dt.date) == [self.BASE, self.MID, self.END]

    def test_sorted_datetime64_with_trailing_nat_uses_scan_path(self):
        # #8131 review: no test pinned that a sorted datetime64 column with a
        # NaT is excluded from the fast path by the `not dates.hasnans` guard.
        col = pd.to_datetime([self.BASE, self.MID, None])
        df = pd.DataFrame({"Date": col, "Close": range(3)})

        result = th.apply_date_range(df, start_date=self.BASE, end_date=self.END)

        assert list(result["Date"].dt.date) == [self.BASE, self.MID]


def _make_frozen_date(frozen_today: dt.date):
    """Return a drop-in replacement for ``datetime.date`` that freezes ``today()``."""

    class _FrozenDate(dt.date):
        @classmethod
        def today(cls):  # type: ignore[override]
            return frozen_today

    return _FrozenDate
