import { describe, expect, it, vi } from "vitest";
import { money, normalizeDisplayCurrency, percentOrNa } from "@/lib/money";

describe("money", () => {
  it("formats a GBP value to the correct string for en-GB locale", () => {
    expect(money(123.45, "GBP", "en-GB")).toBe("£123.45");
  });

  it("returns the em dash sentinel for null", () => {
    expect(money(null, "GBP", "en-GB")).toBe("—");
  });

  it("returns the em dash sentinel for undefined", () => {
    expect(money(undefined, "GBP", "en-GB")).toBe("—");
  });

  it("returns the em dash sentinel for non-finite values", () => {
    expect(money(NaN, "GBP", "en-GB")).toBe("—");
    expect(money(Infinity, "GBP", "en-GB")).toBe("—");
    expect(money(-Infinity, "GBP", "en-GB")).toBe("—");
  });

  it.each(["GBX", "GBXP", "GBPX", "GBpx", "GBp"])(
    "formats pence-code %s as £123.45 (same as GBP)",
    (currency) => {
      expect(money(123.45, currency, "en-GB")).toBe("£123.45");
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
