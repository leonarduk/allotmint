/**
 * Market-calendar judgement for "are these prices stale?" (#7820).
 *
 * Pricing is end-of-day, so on any given day the newest close we can expect
 * to hold is the *previous* London trading day -- today's close lands with the
 * next price refresh. Weekends and England & Wales bank holidays (the LSE
 * calendar) are skipped, so Friday's close viewed on Saturday, Sunday or
 * Monday is not stale. Erring towards "fresh" keeps the warning meaningful:
 * a badge that fires on every load trains people to ignore it.
 *
 * All dates are ISO `YYYY-MM-DD` strings, handled as UTC calendar days so the
 * arithmetic is timezone-independent.
 */

const DAY_MS = 86_400_000;

function parseIsoDay(iso: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  const ms = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(ms) ? null : ms;
}

function toIsoDay(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/** Easter Sunday (anonymous Gregorian algorithm), as a UTC day timestamp. */
function easterSunday(year: number): number {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return Date.UTC(year, month - 1, day);
}

/** First (n=1) or last (n=-1) Monday of a month, as a UTC day timestamp. */
function mondayOf(year: number, month: number, n: 1 | -1): number {
  if (n === 1) {
    const first = Date.UTC(year, month, 1);
    const offset = (8 - new Date(first).getUTCDay()) % 7;
    return first + offset * DAY_MS;
  }
  const last = Date.UTC(year, month + 1, 0);
  const offset = (new Date(last).getUTCDay() + 6) % 7;
  return last - offset * DAY_MS;
}

/** Recurring England & Wales bank holidays for a year (LSE closures). */
function bankHolidays(year: number): Set<number> {
  const days = new Set<number>();
  const shiftOffWeekend = (ms: number) => {
    let day = ms;
    while ([0, 6].includes(new Date(day).getUTCDay()) || days.has(day)) {
      day += DAY_MS;
    }
    days.add(day);
  };
  shiftOffWeekend(Date.UTC(year, 0, 1));
  const easter = easterSunday(year);
  days.add(easter - 2 * DAY_MS);
  days.add(easter + DAY_MS);
  days.add(mondayOf(year, 4, 1));
  days.add(mondayOf(year, 4, -1));
  days.add(mondayOf(year, 7, -1));
  shiftOffWeekend(Date.UTC(year, 11, 25));
  shiftOffWeekend(Date.UTC(year, 11, 26));
  return days;
}

function isTradingDay(ms: number): boolean {
  const weekday = new Date(ms).getUTCDay();
  if (weekday === 0 || weekday === 6) return false;
  return !bankHolidays(new Date(ms).getUTCFullYear()).has(ms);
}

/** The newest close end-of-day pricing is expected to hold on `todayIso`. */
export function lastExpectedClose(todayIso: string): string | null {
  const today = parseIsoDay(todayIso);
  if (today === null) return null;
  let day = today - DAY_MS;
  while (!isTradingDay(day)) day -= DAY_MS;
  return toIsoDay(day);
}

export type PricingFreshness =
  | { stale: false }
  | { stale: true; ageDays: number };

/**
 * Whether `pricingIso` is older than the last expected close as of `todayIso`,
 * and if so its age in calendar days. Unparseable input is reported as fresh
 * rather than raising a warning nobody can act on.
 */
export function pricingFreshness(
  pricingIso: string,
  todayIso: string,
): PricingFreshness {
  const pricing = parseIsoDay(pricingIso);
  const today = parseIsoDay(todayIso);
  const expected = lastExpectedClose(todayIso);
  if (pricing === null || today === null || expected === null) {
    return { stale: false };
  }
  if (pricingIso >= expected) return { stale: false };
  return { stale: true, ageDays: Math.round((today - pricing) / DAY_MS) };
}
