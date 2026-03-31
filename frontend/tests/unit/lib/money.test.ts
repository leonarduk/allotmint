import { describe, expect, it, vi } from "vitest";
import { money, normalizeDisplayCurrency, percentOrNa } from "@/lib/money";

describe("money", () => {
  it.each(["GBX", "GBXP", "GBPX", "GBpx", "GBp"])(
    "formats %s values using pound units",
    (currency) => {
      const value = 123.45;
      expect(money(value, currency, "en-GB")).toBe(
        money(value, "GBP", "en-GB"),
      );
    },
  );
});

describe("normalizeDisplayCurrency", () => {
  it.each(["GBX", "GBXP", "GBPX", "GBpx", "GBp"])(
    "maps pence code %s to GBP",
    (currency) => {
      expect(normalizeDisplayCurrency(currency)).toBe("GBP");
    },
  );

  it("normalises lowercase gbp to GBP (not treated as pence)", () => {
    // "gbp" is lowercase GBP, not a pence code — must return "GBP", not "gbp"
    expect(normalizeDisplayCurrency("gbp")).toBe("GBP");
  });

  it("normalises GBP passthrough to uppercase", () => {
    expect(normalizeDisplayCurrency("GBP")).toBe("GBP");
  });

  it("normalises other currency codes to uppercase", () => {
    expect(normalizeDisplayCurrency("usd")).toBe("USD");
    expect(normalizeDisplayCurrency("USD")).toBe("USD");
  });
});

describe("percentOrNa", () => {
  it("returns N/A without warning for null or undefined", () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(percentOrNa(null)).toBe("N/A");
    expect(percentOrNa(undefined)).toBe("N/A");
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("warns and returns N/A for absurd values", () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(percentOrNa(1200)).toBe("N/A");
    expect(spy).toHaveBeenCalledWith("Metric value out of range:", 1200);
    spy.mockRestore();
  });

  it("formats fractional percentages", () => {
    expect(percentOrNa(0.123)).toBe("12.30%");
  });

  it("normalises whole percentages", () => {
    expect(percentOrNa(3.44)).toBe("3.44%");
  });
});
