import { describe, expect, it } from "vitest";

import { PP_SHARE_SCALE, transactionUnits } from "@/lib/transactionQuantity";

describe("transactionUnits (#10203)", () => {
  it("returns units as real units, whatever their size", () => {
    expect(transactionUnits({ units: 3 })).toBe(3);
    expect(transactionUnits({ units: 2_000_000 })).toBe(2_000_000);
    expect(transactionUnits({ units: -4 })).toBe(-4);
  });

  it("always divides PP shares by 10^8, whatever their size", () => {
    expect(PP_SHARE_SCALE).toBe(100_000_000);
    expect(transactionUnits({ shares: 1_000_000_000 })).toBe(10);
    expect(transactionUnits({ shares: 999_999 })).toBeCloseTo(0.00999999, 10);
    expect(transactionUnits({ shares: 2 })).toBe(2e-8);
  });

  it("prefers units over shares on a PP row edited in the app", () => {
    expect(transactionUnits({ units: 4, shares: 1_000_000_000 })).toBe(4);
  });

  it("returns null when no usable quantity is present", () => {
    expect(transactionUnits({})).toBeNull();
    expect(transactionUnits({ units: null, shares: null })).toBeNull();
    expect(transactionUnits({ shares: Number.NaN })).toBeNull();
    expect(transactionUnits({ units: Number.POSITIVE_INFINITY })).toBeNull();
  });
});
