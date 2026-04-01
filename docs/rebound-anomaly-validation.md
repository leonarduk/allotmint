# Rebound anomaly repair: threshold guidance and validation checklist

Last updated: April 1, 2026.

This note documents how the short-lived anomaly repair logic is tuned and how to validate it against production-like owner datasets.

## Scope

The detector lives in `backend/common/portfolio_utils.py` as `_detect_single_day_flash_crash(...)` and is used by:

- `compute_owner_performance(...)` (owner performance API payloads, including `data_quality_issues`).
- `_portfolio_value_series(...)` (shared analytics path used by drawdown/return helpers).

## Threshold tuning guidance

### `rebound_match_tolerance`

- Meaning: maximum relative difference allowed between the two endpoint values (`prev` and `nxt`) for a short-lived window to be considered a recovery.
- Example: `0.12` means endpoints may differ by up to 12%.
- Guidance:
  - Start conservative (`0.05` to `0.10`) if false positives are observed.
  - Increase only if true anomalies are missed because normal drift between endpoints is too large.

### `rebound_drop_pct_threshold`

- Meaning: minimum interior drop magnitude (fraction of endpoint baseline) to classify as a rebound-drop anomaly.
- Example: `0.12` means at least a 12% interior drop versus baseline.
- Guidance:
  - Lower values catch more dips but increase false positives on real drawdowns.
  - Higher values reduce smoothing and should be used for risk-sensitive analytics.

### `rebound_jump_pct_threshold`

- Meaning: minimum interior spike magnitude (fraction above endpoint baseline) to classify as an upward-spike anomaly.
- Defaults to `rebound_drop_pct_threshold` when omitted.
- Guidance:
  - Keep equal to drop threshold for symmetric behavior.
  - Raise it if upward needles should be tolerated more than downward dips.

### Shared analytics (`_portfolio_value_series`) is intentionally conservative

In `_portfolio_value_series`, repair is run with:

- `rebound_drop_pct_threshold=1.0`
- `rebound_jump_pct_threshold=1.0`

This effectively limits that path to near-zero glitch repair and avoids interpolating legitimate portfolio drawdowns/spikes in risk-style metrics.

## Real/account dataset validation checklist (issue #2686)

Run for a representative set of recent owners (e.g. 3–10 accounts with varied volatility):

1. Capture baseline payloads for `compute_owner_performance(owner, days=365)`:
   - `history` length
   - `max_drawdown`
   - `data_quality_issues` count + sample entries.
2. Verify chart-level outcomes:
   - no single-day “needle” spikes/dips caused by bad prints,
   - no smoothing of obvious genuine multi-day drawdowns.
3. Confirm issue semantics:
   - repaired points appear in `data_quality_issues`,
   - `previous_value`/`next_value` are plausible endpoints.
4. Compare at least one volatile owner against a no-repair baseline (debug run) to confirm real drawdowns are preserved.
5. Record owner/date examples and final threshold decision in issue #2686.

## Environment note for local OSS/dev runs

In this repository snapshot, account fixture files for real owners may be absent (for example under `data/accounts/alice` and `data/accounts/demo-owner`), which can block step 1 for true account-level validation.

If account files are missing, run unit/integration fixtures locally and perform the real-account pass in an environment that has the expected account data mounted.
