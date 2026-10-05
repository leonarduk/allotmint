import { describe, it, expect } from "vitest";
import { priceDecimals } from "./priceFormatting";

describe("priceDecimals", () => {
  it("returns 5 decimals for FX rate pairs (=X suffix)", () => {
    expect(priceDecimals("EURGBP=X", 0.85721)).toBe(5);
    expect(priceDecimals("USDGBP=X", 0.79)).toBe(5);
    // FX rule wins even for large values.
    expect(priceDecimals("EURGBP=X", 15000)).toBe(5);
  });

  it("returns 3 decimals for ^TNX", () => {
    expect(priceDecimals("^TNX", 4.123)).toBe(3);
    expect(priceDecimals("^TNX", 15000)).toBe(3);
  });

  it("returns 5 decimals for sub-$1 crypto pairs", () => {
    expect(priceDecimals("BTC-USD", 0.5)).toBe(5);
    expect(priceDecimals("BTC-USD", 0.00012)).toBe(5);
  });

  it("returns 2 decimals for normal crypto pairs above $1", () => {
    expect(priceDecimals("BTC-USD", 42000)).toBe(0); // >10000 rule
    expect(priceDecimals("BTC-USD", 124)).toBe(2);
  });

  it("uses refPrice (not val) for the sub-$1 crypto check", () => {
    // A negative change on a sub-$1 crypto should still get 5dp.
    expect(priceDecimals("BTC-USD", -0.00012, 0.5)).toBe(5);
    // A large change on a >$1 crypto should get 2dp, not 5dp.
    expect(priceDecimals("BTC-USD", -124, 42000)).toBe(2);
    expect(priceDecimals("BTC-USD", 124, 42000)).toBe(2);
  });

  it("returns 0 decimals for values greater than 10000", () => {
    expect(priceDecimals("^FTSE", 15000)).toBe(0);
    expect(priceDecimals("^GSPC", 5000)).toBe(2);
    expect(priceDecimals("VUSA.L", 10001)).toBe(0);
    expect(priceDecimals("VUSA.L", 10000)).toBe(2);
  });

  it("returns 2 decimals for normal prices", () => {
    expect(priceDecimals("VUSA.L", 75.42)).toBe(2);
    expect(priceDecimals("^FTSE", 7500)).toBe(2);
    expect(priceDecimals("GC=F", 1900)).toBe(2);
  });
});
