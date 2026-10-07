import { describe, it, expect } from "vitest";
import { lastExpectedClose, pricingFreshness } from "@/lib/pricingFreshness";

describe("lastExpectedClose", () => {
  it("is the previous weekday on Tuesday-Friday", () => {
    expect(lastExpectedClose("2026-09-22")).toBe("2026-09-21");
    expect(lastExpectedClose("2026-09-25")).toBe("2026-09-24");
  });

  it("is Friday on Saturday, Sunday and Monday", () => {
    expect(lastExpectedClose("2026-09-19")).toBe("2026-09-18");
    expect(lastExpectedClose("2026-09-20")).toBe("2026-09-18");
    expect(lastExpectedClose("2026-09-21")).toBe("2026-09-18");
  });

  it("skips England & Wales bank holidays", () => {
    // Easter 2026: Good Friday 3 Apr, Easter Monday 6 Apr.
    expect(lastExpectedClose("2026-04-07")).toBe("2026-04-02");
    // Summer bank holiday: last Monday of August.
    expect(lastExpectedClose("2026-09-01")).toBe("2026-08-28");
    // Christmas 2026 is a Friday; Boxing Day (Sat) moves to Monday 28th.
    expect(lastExpectedClose("2026-12-29")).toBe("2026-12-24");
    // New Year's Day 2028 is a Saturday, observed Monday 3 Jan.
    expect(lastExpectedClose("2028-01-04")).toBe("2027-12-31");
  });

  it("returns null for malformed input", () => {
    expect(lastExpectedClose("not-a-date")).toBeNull();
  });
});

describe("pricingFreshness", () => {
  it("does not flag Friday's close over the weekend or on Monday", () => {
    for (const today of ["2026-09-19", "2026-09-20", "2026-09-21"]) {
      expect(pricingFreshness("2026-09-18", today)).toEqual({ stale: false });
    }
  });

  it("flags pricing older than the last expected close with its age", () => {
    expect(pricingFreshness("2026-09-18", "2026-09-22")).toEqual({
      stale: true,
      ageDays: 4,
    });
    expect(pricingFreshness("2026-09-02", "2026-09-18")).toEqual({
      stale: true,
      ageDays: 16,
    });
  });

  it("treats unparseable input as fresh", () => {
    expect(pricingFreshness("garbage", "2026-09-22")).toEqual({ stale: false });
  });
});
