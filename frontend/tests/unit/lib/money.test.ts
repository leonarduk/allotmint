import { describe, expect, it } from "vitest";
import { money, normalizeDisplayCurrency } from "@/lib/money";

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

