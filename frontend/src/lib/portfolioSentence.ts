import type { TFunction } from "i18next";
import { percent } from "./money";
import { classifyMetric, RETURN_RANGE } from "./metricPlausibility";

export type PortfolioSentenceInput = {
  totalValue: number;
  totalDayChange: number;
  /** False when no holding reported a day change, so 0 would mean "no data". */
  hasDayChange: boolean;
  /** Some holding has no price (#8607), so its day move is missing from the total. */
  hasUnpricedHoldings: boolean;
  /** One-year time-weighted return as a fraction; null when unknown or still loading. */
  oneYearTwr: number | null;
};

/** "up £3,375" / "down 0.36%" / "unchanged": the direction word around an absolute figure. */
const direction = (t: TFunction, value: number, amount: string): string =>
  value > 0
    ? t("portfolioSentence.up", { amount })
    : value < 0
      ? t("portfolioSentence.down", { amount })
      : t("portfolioSentence.unchanged");

/** The day clause, or null when the day change is missing or would be misleading. */
const dayClause = (
  t: TFunction,
  input: PortfolioSentenceInput,
  formatMoney: (value: number) => string,
): string | null => {
  const { totalValue, totalDayChange, hasDayChange, hasUnpricedHoldings } = input;
  if (!hasDayChange || hasUnpricedHoldings || !Number.isFinite(totalDayChange)) return null;
  const baseline = totalValue - totalDayChange;
  if (!Number.isFinite(baseline) || baseline <= 0) return null;
  const pct = percent(Math.abs((totalDayChange / baseline) * 100));
  return direction(t, totalDayChange, `${formatMoney(Math.abs(totalDayChange))} (${pct})`);
};

/** The one-year clause, or null when the return is unknown or implausible. */
const yearClause = (t: TFunction, twr: number | null): string | null => {
  if (twr === null || classifyMetric(twr, RETURN_RANGE) !== "ok") return null;
  return direction(t, twr, percent(Math.abs(twr * 100), 1));
};

/**
 * A one-sentence, plain-English portfolio summary (#7826), e.g. "Your
 * portfolio is worth £1,148,730 — down £3,375 (0.36%) today, and up 15.4%
 * over the past year." Each clause appears only when its data is known: a
 * missing figure is left out, never printed as zero. Null when there is no
 * value to describe.
 */
export function buildPortfolioSentence(
  t: TFunction,
  input: PortfolioSentenceInput,
  formatMoney: (value: number) => string,
): string | null {
  if (!Number.isFinite(input.totalValue)) return null;
  const value = formatMoney(input.totalValue);
  const day = dayClause(t, input, formatMoney);
  const year = yearClause(t, input.oneYearTwr);
  if (day && year) return t("portfolioSentence.withDayAndYear", { value, day, year });
  if (day) return t("portfolioSentence.withDay", { value, day });
  if (year) return t("portfolioSentence.withYear", { value, year });
  return t("portfolioSentence.valueOnly", { value });
}
