/**
 * The Season Track — a tiered milestone ladder over the UK tax year.
 *
 * Like the domain model in `plotModel.ts`, everything here is pure and free
 * of network access. The season is not an invented event window: it is the
 * real UK tax year reported by `GET /tax/allowances`, which runs 6 April to
 * 5 April and is when unused ISA and pension allowances actually expire.
 */

import {
  ALLOWANCES_UNAVAILABLE_MESSAGE,
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
  /**
   * True when this goal's underlying data (currently only the allowances
   * feed) failed to load, so the UI should show a distinct error notice
   * instead of a "0 of target" progress bar (#7005).
   */
  unavailable?: boolean;
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
  /**
   * Bare, unit-less variant of `format` for the compact tier-chip row
   * (`✓ 5  ✓ 10  25  50`). Defaults to `format` — money and level labels are
   * already compact there. Groups whose `format` spells out a unit word
   * ("crop(s)", "day(s)") override this so the unit shows once, on the goal
   * line, rather than once per chip (#7194).
   */
  chipFormat?: (value: number) => string;
  unavailable?: boolean;
}

/**
 * Round `value` and pluralise `unit` against it, e.g. `1 day` / `3 days`.
 * Shared by every group whose figure is a plain count rather than money or a
 * level, so a goal never renders as a bare, unit-less number (#7194).
 */
const pluralize = (value: number, unit: string): string => {
  const rounded = Math.round(value);
  return `${rounded} ${unit}${rounded === 1 ? '' : 's'}`;
};

/**
 * The shared per-category ladder both `buildSeasonGoals` (one row per tier,
 * used by the flat milestone list) and `buildSeasonGroups` (one row per
 * category, used by the Season page's collapsed view) are built from — kept
 * in one place so the two never drift on tier thresholds or reward copy.
 */
function buildGoalGroups(
  snapshot: PlotSnapshot,
  allowances: AllowanceMap | null,
  allowancesUnavailable = false
): GoalGroup[] {
  const allowanceRows = Object.values(allowances ?? {});
  const allowanceUsed = allowanceRows.reduce(
    (sum, row) => sum + (row.used ?? 0),
    0
  );

  return [
    {
      id: 'tend',
      group: 'Tend the plot',
      rewardIcon: '🌱',
      rewardLabel: 'Grower badge',
      tiers: [5, 10, 25, 50],
      current: snapshot.crops.length,
      title: (target) => `Tend ${target} crops at once`,
      format: (value) => pluralize(value, 'crop'),
      chipFormat: (value) => String(Math.round(value)),
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
      unavailable: allowancesUnavailable,
    },
    {
      id: 'streak',
      group: 'Keep the streak',
      rewardIcon: '🔥',
      rewardLabel: 'Streak badge',
      tiers: [3, 7, 14, 30],
      current: snapshot.streak,
      title: (target) => `Hold a ${target}-day chore streak`,
      format: (value) => pluralize(value, 'day'),
      chipFormat: (value) => String(Math.round(value)),
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
}

/**
 * Build the ladder. Every `current` value comes from a figure the plot
 * snapshot already holds, so a goal can never show progress the portfolio
 * does not actually have.
 */
export function buildSeasonGoals(
  snapshot: PlotSnapshot,
  allowances: AllowanceMap | null,
  allowancesUnavailable = false
): SeasonGoal[] {
  const groups = buildGoalGroups(snapshot, allowances, allowancesUnavailable);

  return groups.flatMap((group) =>
    group.tiers.map((target) => ({
      id: `${group.id}-${target}`,
      group: group.group,
      title: group.title(target),
      current: group.current,
      target,
      pct: target > 0 ? clamp((group.current / target) * 100, 0, 100) : 0,
      complete: !group.unavailable && group.current >= target,
      display: group.unavailable
        ? ALLOWANCES_UNAVAILABLE_MESSAGE
        : group.format(group.current),
      rewardIcon: group.rewardIcon,
      rewardLabel: group.rewardLabel,
      unavailable: group.unavailable,
    }))
  );
}

export interface SeasonTierBadge {
  target: number;
  /**
   * The tier's target formatted for the compact chip row, e.g. "£10.0k" or
   * "25" — bare for groups whose full format spells out a unit word, so six
   * repeats of "crops"/"days" don't wrap the row (#7194).
   */
  displayTarget: string;
  complete: boolean;
}

export interface SeasonGroupProgress {
  id: string;
  group: string;
  rewardIcon: string;
  rewardLabel: string;
  /** The real current figure, formatted for its unit. */
  currentDisplay: string;
  /** Every tier in the ladder, for the compact earned/unearned badge row. */
  tiers: SeasonTierBadge[];
  /**
   * Progress toward the first tier not yet earned. `null` once every tier in
   * the group is cleared — there is no "next" goal left to show a bar for.
   * `title` is the human description of that tier, e.g. "Tend 25 crops at
   * once" — the thing the screen should actually say the goal is (#7194).
   */
  next: {
    target: number;
    displayTarget: string;
    pct: number;
    title: string;
  } | null;
  /** True once every tier in the group has been earned. */
  complete: boolean;
  /**
   * True when this group's underlying data (currently only the allowances
   * feed, for "Feed the beds") failed to load, so the UI should show a
   * distinct error notice instead of a progress bar (#7005).
   */
  unavailable?: boolean;
}

/**
 * One row per category (not per tier), each tracking progress toward the
 * next tier that has not been earned yet. Earned tiers collapse into a
 * compact badge rather than repeating the same current value against a
 * target the grower has already cleared — see #7006.
 */
export function buildSeasonGroups(
  snapshot: PlotSnapshot,
  allowances: AllowanceMap | null,
  allowancesUnavailable = false
): SeasonGroupProgress[] {
  const groups = buildGoalGroups(snapshot, allowances, allowancesUnavailable);

  return groups.map((group) => {
    const chipFormat = group.chipFormat ?? group.format;
    const tiers = group.tiers.map((target) => ({
      target,
      displayTarget: chipFormat(target),
      complete: group.current >= target,
    }));
    const nextTarget = group.tiers.find((target) => group.current < target);
    const next =
      nextTarget === undefined
        ? null
        : {
            target: nextTarget,
            displayTarget: group.format(nextTarget),
            pct: clamp((group.current / nextTarget) * 100, 0, 100),
            title: group.title(nextTarget),
          };

    return {
      id: group.id,
      group: group.group,
      rewardIcon: group.rewardIcon,
      rewardLabel: group.rewardLabel,
      currentDisplay: group.format(group.current),
      tiers,
      next,
      complete: next === null,
      unavailable: group.unavailable,
    };
  });
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
