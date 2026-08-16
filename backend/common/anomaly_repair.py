"""Single-day rebound anomaly detection and repair.

Extracted from ``backend.common.portfolio_utils`` (issue #2686) so this file's
history can be split cleanly into the private ``allotmint-core`` package
without dragging the rest of ``portfolio_utils.py`` along with it. See
``docs/rebound-anomaly-validation.md`` for the validation methodology behind
the thresholds below.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

import pandas as pd


def _detect_single_day_flash_crash(
    series: pd.Series,
    *,
    absolute_threshold: float = 1.0,
    relative_threshold: float = 0.01,
    rebound_drop_pct_threshold: float = 0.12,
    rebound_jump_pct_threshold: float | None = None,
    rebound_match_tolerance: float = 0.12,
    max_rebound_span: int = 3,
) -> Tuple[pd.Series, List[Dict[str, Any]]]:
    """Interpolate short-lived rebound anomalies (up to ``max_rebound_span`` days).

    Detection modes:
    - Near-zero glitch: interior point falls below ``absolute_threshold`` or
      ``relative_threshold`` of the lower neighbour.
    - Rebound drop: interior point(s) drop by at least
      ``rebound_drop_pct_threshold`` while the window endpoints remain within
      ``rebound_match_tolerance`` of each other.
    - Rebound jump: interior point(s) spike above neighbours by at least
      ``rebound_jump_pct_threshold`` (or ``rebound_drop_pct_threshold`` when
      omitted), with the same endpoint recovery check.

    Tuning notes:
    - ``rebound_match_tolerance`` is a fractional endpoint-difference threshold.
      For example, 0.12 allows endpoints to differ by up to 12%.
    - ``rebound_drop_pct_threshold`` / ``rebound_jump_pct_threshold`` are
      fractional interior deviations from the endpoint baseline.
    - For conservative paths (e.g. drawdown analytics), prefer higher drop/jump
      thresholds so only near-zero glitches are repaired.
    """

    if series.empty:
        return series, []

    values = pd.to_numeric(series.sort_index(), errors="coerce")
    repaired = values.astype(float).copy()
    issues: List[Dict[str, Any]] = []
    repaired_indices: set[Any] = set()
    jump_threshold = rebound_drop_pct_threshold if rebound_jump_pct_threshold is None else rebound_jump_pct_threshold

    epsilon = 1e-9
    for start_idx in range(0, len(values) - 1):
        prev = float(repaired.iloc[start_idx])
        if not math.isfinite(prev) or prev <= 0:
            continue

        for span in range(1, max_rebound_span + 1):
            end_idx = start_idx + span + 1
            if end_idx >= len(values):
                break

            nxt = float(repaired.iloc[end_idx])
            if not math.isfinite(nxt) or nxt <= 0:
                continue

            min_neighbor = min(prev, nxt)
            neighbor_baseline = min_neighbor if min_neighbor > epsilon else 1.0
            neighbors_recovered = abs(prev - nxt) / neighbor_baseline <= rebound_match_tolerance
            if not neighbors_recovered:
                continue

            window = repaired.iloc[start_idx + 1 : end_idx]
            if window.empty:
                continue
            finite_window = window[pd.to_numeric(window, errors="coerce").notna()]
            if finite_window.empty:
                continue

            window_min = float(finite_window.min())
            window_max = float(finite_window.max())
            max_neighbor = max(prev, nxt)
            resembles_zero_glitch = window_min <= absolute_threshold or window_min <= min_neighbor * relative_threshold
            drop_pct = 1 - (window_min / min_neighbor)
            jump_pct = (window_max / max_neighbor) - 1 if max_neighbor > epsilon else 0.0
            large_short_lived_drop = drop_pct >= rebound_drop_pct_threshold
            large_short_lived_jump = jump_pct >= jump_threshold
            if not (resembles_zero_glitch or large_short_lived_drop or large_short_lived_jump):
                continue

            span_len = len(window)
            repaired_any = False
            for offset, (label, value) in enumerate(window.items(), start=1):
                if label in repaired_indices:
                    continue
                if not pd.notna(value):
                    continue
                point = float(value)
                point_drop_pct = 1 - (point / min_neighbor)
                point_jump_pct = (point / max_neighbor) - 1 if max_neighbor > epsilon else 0.0
                is_zero_like = point <= absolute_threshold or point <= min_neighbor * relative_threshold
                is_large_drop = point_drop_pct >= rebound_drop_pct_threshold
                is_large_jump = point_jump_pct >= jump_threshold
                if not (is_zero_like or is_large_drop or is_large_jump):
                    continue
                repaired_value = prev + ((nxt - prev) * (offset / (span_len + 1)))
                iso_date = label.isoformat() if hasattr(label, "isoformat") else str(label)
                issues.append(
                    {
                        "date": iso_date,
                        "value": round(float(value), 2),
                        "repaired_value": round(float(repaired_value), 2),
                        "previous_value": round(prev, 2),
                        "next_value": round(nxt, 2),
                    }
                )
                repaired.loc[label] = repaired_value
                repaired_indices.add(label)
                repaired_any = True
            if repaired_any:
                break

    return repaired, issues
