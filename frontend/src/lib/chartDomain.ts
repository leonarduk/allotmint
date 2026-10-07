/**
 * A y-axis domain that fits ``values`` instead of starting at 0 (#7815).
 *
 * A ~£72k portfolio on a 0 → 80k axis renders a year of movement as a flat
 * line, so the axis hugs the data with 10% padding either side. The visible
 * span is never narrower than ``minSpanFraction`` of the series' magnitude,
 * so ordinary daily noise on a near-flat series is not blown up into
 * dramatic-looking swings. The ends snap outward to a round step so ticks
 * read £67,500 rather than £68,815. A non-negative series never gets a
 * negative floor.
 *
 * Returns ``undefined`` when there is nothing finite to fit, letting the
 * chart fall back to its default domain.
 */
export function paddedDomain(
  values: ReadonlyArray<number | null | undefined>,
  minSpanFraction = 0.1,
): [number, number] | undefined {
  const finite = values.filter(
    (v): v is number => typeof v === "number" && Number.isFinite(v),
  );
  if (finite.length === 0) return undefined;
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const range = max - min;
  const magnitude = Math.max(Math.abs(min), Math.abs(max));
  const pad = Math.max(range * 0.1, (magnitude * minSpanFraction - range) / 2);
  // Only reachable for an all-zero series (any other value gives a non-zero
  // min-span pad); it still keeps the non-negative floor.
  if (pad === 0) return [0, 1];
  const lower = min >= 0 ? Math.max(0, min - pad) : min - pad;
  const upper = max + pad;
  const step = niceStep((upper - lower) / 4);
  return [snap(Math.floor(lower / step) * step), snap(Math.ceil(upper / step) * step)];
}

/** Drop float noise such as 0.30000000000000004 from a snapped bound. */
function snap(value: number): number {
  return Number(value.toPrecision(12));
}

/** The smallest 1/2/2.5/5 x 10^n step at or above ``rough``. */
function niceStep(rough: number): number {
  const exponent = 10 ** Math.floor(Math.log10(rough));
  const nice = [1, 2, 2.5, 5].find((f) => rough / exponent <= f) ?? 10;
  return nice * exponent;
}
