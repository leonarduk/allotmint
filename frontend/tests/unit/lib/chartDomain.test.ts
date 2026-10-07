import { describe, expect, it } from "vitest";
import { paddedDomain } from "@/lib/chartDomain";

describe("paddedDomain", () => {
  it("fits a ~£72k series instead of starting the axis at 0 (#7815)", () => {
    // Padded to 58,800..73,200, then snapped outward to a 5,000 step.
    expect(paddedDomain([60000, 66000, 72000])).toEqual([55000, 75000]);
  });

  it("snaps the ends to round tick values", () => {
    // Padded to 68,770..76,330, then snapped outward to a 2,000 step.
    expect(paddedDomain([69500, 75600])).toEqual([68000, 78000]);
  });

  it("keeps a minimum span so daily noise on a flat series is not exaggerated", () => {
    // A 0.5% wobble on £72k still sits on an axis spanning 10%+ of the value.
    const [lower, upper] = paddedDomain([72000, 72360])!;
    expect(upper - lower).toBeGreaterThanOrEqual(7236);
    expect(lower).toBeLessThan(72000);
    expect(upper).toBeGreaterThan(72360);
  });

  it("never gives a non-negative series a negative floor", () => {
    expect(paddedDomain([10, 1000])![0]).toBe(0);
  });

  it("pads a negative series below its minimum", () => {
    expect(paddedDomain([-100, -50])).toEqual([-120, -40]);
  });

  it("ignores non-finite values and returns undefined when nothing is plottable", () => {
    expect(paddedDomain([null, undefined, NaN])).toBeUndefined();
    expect(paddedDomain([])).toBeUndefined();
    expect(paddedDomain([null, 100, 200])).toEqual([50, 250]);
  });

  it("gives an all-zero series a non-degenerate, non-negative domain", () => {
    expect(paddedDomain([0, 0])).toEqual([0, 1]);
  });

  it("snaps fractional bounds without floating-point noise", () => {
    // Step 0.05: raw multiplication would give 0.15000000000000002.
    expect(paddedDomain([0.2, 0.3])).toEqual([0.15, 0.35]);
  });
});
