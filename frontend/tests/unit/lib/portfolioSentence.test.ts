import { describe, expect, it } from "vitest";
import i18n from "@/i18n";
import { buildPortfolioSentence, type PortfolioSentenceInput } from "@/lib/portfolioSentence";
import { money } from "@/lib/money";

const t = i18n.getFixedT("en");
const gbp = (value: number) => money(value, "GBP", "en-GB");

const base: PortfolioSentenceInput = {
  totalValue: 1_148_730,
  totalDayChange: -3_375,
  hasDayChange: true,
  hasUnpricedHoldings: false,
  oneYearTwr: 0.154,
};

const sentence = (overrides: Partial<PortfolioSentenceInput> = {}) =>
  buildPortfolioSentence(t, { ...base, ...overrides }, gbp);

describe("buildPortfolioSentence (#7826)", () => {
  it("states value, day change and one-year return in one sentence", () => {
    // Day % is over the start-of-day value: 3,375 / (1,148,730 + 3,375).
    expect(sentence()).toBe(
      "Your portfolio is worth £1,148,730.00 — down £3,375.00 (0.29%) today, and up 15.4% over the past year.",
    );
  });

  it("says up for a rise and down for a negative return", () => {
    expect(sentence({ totalDayChange: 1_000, oneYearTwr: -0.052 })).toBe(
      "Your portfolio is worth £1,148,730.00 — up £1,000.00 (0.09%) today, and down 5.2% over the past year.",
    );
  });

  it("omits the year clause while the return is loading or unknown", () => {
    expect(sentence({ oneYearTwr: null })).toBe(
      "Your portfolio is worth £1,148,730.00 — down £3,375.00 (0.29%) today.",
    );
  });

  it("omits an implausible return rather than printing it", () => {
    expect(sentence({ oneYearTwr: 141.59 })).not.toMatch(/past year/);
  });

  it("omits the day clause when no holding has a day change", () => {
    expect(sentence({ totalDayChange: 0, hasDayChange: false })).toBe(
      "Your portfolio is worth £1,148,730.00 — up 15.4% over the past year.",
    );
  });

  it("omits the day clause when a holding is unpriced", () => {
    expect(sentence({ hasUnpricedHoldings: true })).not.toMatch(/today/);
  });

  it("omits the day clause when there is no start-of-day value to compare with", () => {
    expect(sentence({ totalValue: 500, totalDayChange: 500 })).not.toMatch(/today/);
  });

  it("states only the value when nothing else is known, never a zero", () => {
    const text = sentence({ hasDayChange: false, totalDayChange: 0, oneYearTwr: null });
    expect(text).toBe("Your portfolio is worth £1,148,730.00.");
    expect(text).not.toMatch(/0\.00%/);
  });

  it("calls a genuine zero day change unchanged", () => {
    expect(sentence({ totalDayChange: 0, oneYearTwr: null })).toBe(
      "Your portfolio is worth £1,148,730.00 — unchanged today.",
    );
  });

  it("returns null without a finite value", () => {
    expect(sentence({ totalValue: Number.NaN })).toBeNull();
  });
});
