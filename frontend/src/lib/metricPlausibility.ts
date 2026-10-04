// Every headline performance metric is returned by the API as a FRACTION
// (0.0596 = 5.96%) -- alpha, tracking error, max drawdown, TWR and XIRR,
// on the owner AND the group routes (see the unit audit on #8570, pinned by
// tests/test_performance_routes.py). Format them directly from that unit:
// never guess "|x| > 1 means percent, so divide by 100" -- that turned a
// broken 14159.17 XIRR into a believable 141.59% and a genuine 1.5 (150%)
// into 1.5%.
//
// Instead, values outside these bounds are treated as an unreliable
// calculation and rendered as "N/A" with a tooltip, never rescaled.

export type PlausibleRange = { min: number; max: number };

/** |TWR|, |XIRR| or |alpha| above 10 (1,000%) is not a believable return. */
export const MAX_PLAUSIBLE_ABS_RETURN = 10;
/** Annualised tracking error / volatility is a std-dev (>= 0); above 2 (200%) is implausible. */
export const MAX_PLAUSIBLE_STD_DEV = 2;

export const RETURN_RANGE: PlausibleRange = {
  min: -MAX_PLAUSIBLE_ABS_RETURN,
  max: MAX_PLAUSIBLE_ABS_RETURN,
};
export const TRACKING_ERROR_RANGE: PlausibleRange = {
  min: 0,
  max: MAX_PLAUSIBLE_STD_DEV,
};
export const VOLATILITY_RANGE: PlausibleRange = TRACKING_ERROR_RANGE;
/** Drawdown is peak-relative, so it can only lie in [-1, 0] (-100%..0%). */
export const DRAWDOWN_RANGE: PlausibleRange = { min: -1, max: 0 };

export const isFiniteNumber = (value: number | null | undefined): value is number =>
  typeof value === "number" && Number.isFinite(value);

export const isPlausible = (value: number, range: PlausibleRange) =>
  value >= range.min && value <= range.max;

/**
 * Single source of truth for how a metric value is treated:
 * - "missing": null/undefined/NaN/Infinity -> plain "N/A";
 * - "unreliable": finite but outside the plausible range -> "N/A" with an
 *   "unreliable" tooltip (never rescaled);
 * - "ok": formatted as a percentage.
 */
export type MetricState = "missing" | "unreliable" | "ok";

export const classifyMetric = (
  value: number | null | undefined,
  range: PlausibleRange,
): MetricState => {
  if (!isFiniteNumber(value)) return "missing";
  return isPlausible(value, range) ? "ok" : "unreliable";
};

/** A plausible drawdown at or beyond -90% usually means bad price data. */
export const SEVERE_DRAWDOWN = -0.9;

export type DrawdownState = MetricState | "severe";

/** Classify max drawdown; "severe" is a plausible value <= -90%. */
export const classifyDrawdown = (value: number | null | undefined): DrawdownState => {
  const state = classifyMetric(value, DRAWDOWN_RANGE);
  if (state === "ok" && (value as number) <= SEVERE_DRAWDOWN) return "severe";
  return state;
};

/** Severe or unreliable drawdowns warrant drawing the user's attention. */
export const drawdownNeedsAttention = (state: DrawdownState) =>
  state === "severe" || state === "unreliable";
