/**
 * The Season Track — a tiered milestone ladder over the UK tax year.
 *
 * Like the domain model in `plotModel.ts`, everything here is pure and free
 * of network access. The season is not an invented event window: it is the
 * real UK tax year reported by `GET /tax/allowances`, which runs 6 April to
 * 5 April and is when unused ISA and pension allowances actually expire.
 */

import {
  clamp,
  formatGbp,
  type AllowanceMap,
  type PlotSnapshot,
} from './plotModel';

export interface Season {
  /** Human label, e.g. "2026/27". */
  label: string;
  /** Last day of the tax year (5 April), as an ISO date. */
  endsOn: string;
}

/**
 * Parse the backend's `"YYYY-YYYY"` tax-year string into a season window.
 *
 * The UK tax year ends on 5 April of the second year (see
 * `allotmint_pro.allowances.current_tax_year`). Returns null for anything
 * that does not parse, so a missing or unexpected value degrades to "no
 * season" rather than a wrong deadline.
 */
export function parseTaxYear(
  taxYear: string | null | undefined
): Season | null {
  const match = /^(\d{4})-(\d{4})$/.exec((taxYear ?? '').trim());
  if (!match) return null;
  const startYear = Number(match[1]);
  const endYear = Number(match[2]);
  if (endYear !== startYear + 1) return null;
  return {
    label: `${startYear}/${String(endYear).slice(-2)}`,
    endsOn: `${endYear}-04-05`,
  };
}

export interface SeasonCountdown {
  days: number;
  hours: number;
  expired: boolean;
  /** Ready-to-render caption, e.g. "Ends in 224 days and 7 hours". */
  label: string;
}

/**
 * Time left in the season. `now` is a parameter rather than a `Date.now()`
 * call so the countdown is deterministic under test.
 */
export function seasonCountdown(season: Season, now: Date): SeasonCountdown {
  // The tax year ends at the close of 5 April, so the deadline is the start
  // of the 6th.
  const deadline = new Date(`${season.endsOn}T00:00:00Z`);
  deadline.setUTCDate(deadline.getUTCDate() + 1);
  const remainingMs = deadline.getTime() - now.getTime();

  if (!Number.isFinite(remainingMs) || remainingMs <= 0) {
    return { days: 0, hours: 0, expired: true, label: 'Season closed' };
  }

  const days = Math.floor(remainingMs / 86_400_000);
  const hours = Math.floor((remainingMs % 86_400_000) / 3_600_000);
  const dayPart = `${days} day${days === 1 ? '' : 's'}`;
  const hourPart = `${hours} hour${hours === 1 ? '' : 's'}`;
  return {
    days,
    hours,
    expired: false,
    label:
      days > 0 ? `Ends in ${dayPart} and ${hourPart}` : `Ends in ${hourPart}`,
  };
}

export interface SeasonGoal {
  id: string;
  group: string;
  title: string;
  current: number;
  target: number;
  /** 0–100. */
  pct: number;
  complete: boolean;
  /**
   * The real current figure formatted for its unit, shown beside the bar.
   * Deliberately not clamped to the target: on a tier already cleared, the
   * true value ("8 crops" against a 5-crop goal) is more use than echoing
   * the target back.
   */
  display: string;
  rewardIcon: string;
  rewardLabel: string;
}

interface GoalGroup {
  id: string;
  group: string;
  rewardIcon: string;
  rewardLabel: string;
  tiers: number[];
  current: number;
  title: (target: number) => string;
  format: (value: number) => string;
}

const countFormat = (value: number) => String(Math.round(value));

/**
 * Build the ladder. Every `current` value comes from a figure the plot
 * snapshot already holds, so a goal can never show progress the portfolio
 * does not actually have.
 */
export function buildSeasonGoals(
  snapshot: PlotSnapshot,
  allowances: AllowanceMap | null
): SeasonGoal[] {
  const allowanceRows = Object.values(allowances ?? {});
  const allowanceUsed = allowanceRows.reduce(
    (sum, row) => sum + (row.used ?? 0),
    0
  );

  const groups: GoalGroup[] = [
    {
      id: 'tend',
      group: 'Tend the plot',
      rewardIcon: '🌱',
      rewardLabel: 'Grower badge',
      tiers: [5, 10, 25, 50],
      current: snapshot.crops.length,
      title: (target) => `Tend ${target} crops at once`,
      format: countFormat,
    },
    {
      id: 'grow',
      group: 'Grow the plot',
      rewardIcon: '🧺',
      rewardLabel: 'Harvest badge',
      tiers: [1_000, 10_000, 50_000, 250_000],
      current: snapshot.plotValueGbp,
      title: (target) => `Grow the plot to ${formatGbp(target)}`,
      format: formatGbp,
    },
    {
      id: 'feed',
      group: 'Feed the beds',
      rewardIcon: '🌿',
      rewardLabel: 'Feed badge',
      tiers: [1_000, 5_000, 10_000, 20_000],
      current: allowanceUsed,
      title: (target) => `Use ${formatGbp(target)} of this season's allowances`,
      format: formatGbp,
    },
    {
      id: 'streak',
      group: 'Keep the streak',
      rewardIcon: '🔥',
      rewardLabel: 'Streak badge',
      tiers: [3, 7, 14, 30],
      current: snapshot.streak,
      title: (target) => `Hold a ${target}-day chore streak`,
      format: (value) => `${Math.round(value)} days`,
    },
    {
      id: 'rank',
      group: 'Earn your rank',
      rewardIcon: '🎖️',
      rewardLabel: 'Rank badge',
      tiers: [4, 8, 15, 25],
      current: snapshot.grower.level,
      title: (target) => `Reach grower level ${target}`,
      format: (value) => `Level ${Math.round(value)}`,
    },
  ];

  return groups.flatMap((group) =>
    group.tiers.map((target) => ({
      id: `${group.id}-${target}`,
      group: group.group,
      title: group.title(target),
      current: group.current,
      target,
      pct: target > 0 ? clamp((group.current / target) * 100, 0, 100) : 0,
      complete: group.current >= target,
      display: group.format(group.current),
      rewardIcon: group.rewardIcon,
      rewardLabel: group.rewardLabel,
    }))
  );
}

export interface DayStamp {
  /** ISO date. */
  date: string;
  /** Short weekday initial for the label, e.g. "M". */
  initial: string;
  completed: number;
  total: number;
  /** Every daily chore done that day. */
  stamped: boolean;
  /** Some but not all done. */
  partial: boolean;
  isToday: boolean;
}

export type DailyTotals = Record<
  string,
  { completed: number; total: number } | undefined
>;

const WEEKDAY_INITIALS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

/**
 * The last `length` days ending on `today`, stamped from the Trail's real
 * per-day totals. A day the backend has no record for reads as unstamped
 * rather than being filled in with a guess.
 */
export function buildStreakPath(
  dailyTotals: DailyTotals | null | undefined,
  today: string,
  length = 7
): DayStamp[] {
  const anchor = new Date(`${today}T00:00:00Z`);
  if (Number.isNaN(anchor.getTime())) return [];

  const days: DayStamp[] = [];
  for (let offset = length - 1; offset >= 0; offset -= 1) {
    const day = new Date(anchor.getTime());
    day.setUTCDate(day.getUTCDate() - offset);
    const iso = day.toISOString().slice(0, 10);
    const totals = dailyTotals?.[iso];
    const completed = totals?.completed ?? 0;
    const total = totals?.total ?? 0;
    days.push({
      date: iso,
      initial: WEEKDAY_INITIALS[day.getUTCDay()],
      completed,
      total,
      stamped: total > 0 && completed >= total,
      partial: total > 0 && completed > 0 && completed < total,
      isToday: offset === 0,
    });
  }
  return days;
}
