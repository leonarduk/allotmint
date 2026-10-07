/**
 * The Season Track — a tiered milestone ladder over the UK tax year.
 *
 * Like the domain model in `plotModel.ts`, everything here is pure and free
 * of network access. The season is not an invented event window: it is the
 * real UK tax year, which runs 6 April to 5 April and is when unused ISA and
 * pension allowances actually expire. `GET /tax/allowances` reports it when
 * available; otherwise it is derived from the calendar (#7195).
 */

import i18n from '../i18n';
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

/**
 * The UK tax year containing `now`, derived from the calendar alone. The
 * window (6 April – 5 April) is public, so it needs no backend: this is the
 * fallback when `/tax/allowances` is unavailable (e.g. the 402 billing gate
 * on a deployment without the pro package) or omits `tax_year` (#7195).
 * Uses UTC date fields to match `seasonCountdown`'s UTC deadline.
 */
export function seasonFromCalendar(now: Date): Season {
  const year = now.getUTCFullYear();
  const month = now.getUTCMonth(); // 0-based: 3 = April
  const beforeSixthApril =
    month < 3 || (month === 3 && now.getUTCDate() < 6);
  const startYear = beforeSixthApril ? year - 1 : year;
  return {
    label: `${startYear}/${String(startYear + 1).slice(-2)}`,
    endsOn: `${startYear + 1}-04-05`,
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
    return { days: 0, hours: 0, expired: true, label: i18n.t('plot.model.seasonClosed') };
  }

  const days = Math.floor(remainingMs / 86_400_000);
  const hours = Math.floor((remainingMs % 86_400_000) / 3_600_000);
  const dayPart = i18n.t('plot.model.dayCount', { count: days });
  const hourPart = i18n.t('plot.model.hourCount', { count: hours });
  return {
    days,
    hours,
    expired: false,
    label:
      days > 0
        ? i18n.t('plot.model.endsInDaysHours', { days: dayPart, hours: hourPart })
        : i18n.t('plot.model.endsInHours', { hours: hourPart }),
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
  /**
   * Bare, unit-less variant of `format` for the compact tier-chip row
   * (`✓ 5  ✓ 10  25  50`). Defaults to `format`. Chips carry the unit unless
   * repeating it four times in one row is the actual problem: money
   * ("£1.0k") and level ("Level 4") labels are already compact there, and
   * the streak group's "3 days / 7 days / 14 days / 30 days" was never
   * complained about. Only "tend" overrides this — its bare-number chips
   * (`5  10  25  50`) were the one row that visibly wrapped once its goal
   * line picked up a unit (#7194).
   */
  chipFormat?: (value: number) => string;
}

/**
 * Round `value` and pluralise `unit` against it, e.g. `1 day` / `3 days`.
 * Shared by every group whose figure is a plain count rather than money or a
 * level, so a goal never renders as a bare, unit-less number (#7194).
 */
const pluralize = (value: number, unit: 'crop' | 'day'): string =>
  i18n.t(`plot.model.${unit}Count`, { count: Math.round(value) });

/**
 * The shared per-category ladder both `buildSeasonGoals` (one row per tier,
 * used by the flat milestone list) and `buildSeasonGroups` (one row per
 * category, used by the Season page's collapsed view) are built from — kept
 * in one place so the two never drift on tier thresholds or reward copy.
 *
 * When the allowances fetch failed (e.g. the 402 billing gate on a
 * deployment without the pro package), "Feed the beds" is left out entirely
 * rather than shown as four permanently unearnable tiers, so the ladder's
 * denominator only counts milestones the grower can actually reach (#7195).
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

  const groups: GoalGroup[] = [
    {
      id: 'tend',
      group: i18n.t('plot.goals.tend.group'),
      rewardIcon: '🌱',
      rewardLabel: i18n.t('plot.goals.tend.reward'),
      tiers: [5, 10, 25, 50],
      current: snapshot.crops.length,
      title: (target) => i18n.t('plot.goals.tend.title', { target }),
      format: (value) => pluralize(value, 'crop'),
      chipFormat: (value) => String(Math.round(value)),
    },
    {
      id: 'grow',
      group: i18n.t('plot.goals.grow.group'),
      rewardIcon: '🧺',
      rewardLabel: i18n.t('plot.goals.grow.reward'),
      tiers: [1_000, 10_000, 50_000, 250_000],
      current: snapshot.plotValueGbp,
      title: (target) =>
        i18n.t('plot.goals.grow.title', { amount: formatGbp(target) }),
      format: formatGbp,
    },
    {
      id: 'feed',
      group: i18n.t('plot.goals.feed.group'),
      rewardIcon: '🌿',
      rewardLabel: i18n.t('plot.goals.feed.reward'),
      tiers: [1_000, 5_000, 10_000, 20_000],
      current: allowanceUsed,
      title: (target) =>
        i18n.t('plot.goals.feed.title', { amount: formatGbp(target) }),
      format: formatGbp,
    },
    {
      id: 'streak',
      group: i18n.t('plot.goals.streak.group'),
      rewardIcon: '🔥',
      rewardLabel: i18n.t('plot.goals.streak.reward'),
      tiers: [3, 7, 14, 30],
      current: snapshot.streak,
      title: (target) => i18n.t('plot.goals.streak.title', { target }),
      format: (value) => pluralize(value, 'day'),
      chipFormat: (value) => pluralize(value, 'day'),
    },
    {
      id: 'rank',
      group: i18n.t('plot.goals.rank.group'),
      rewardIcon: '🎖️',
      rewardLabel: i18n.t('plot.goals.rank.reward'),
      tiers: [4, 8, 15, 25],
      current: snapshot.grower.level,
      title: (target) => i18n.t('plot.goals.rank.title', { target }),
      format: (value) =>
        i18n.t('plot.model.level', { level: Math.round(value) }),
    },
  ];
  return allowancesUnavailable
    ? groups.filter((group) => group.id !== 'feed')
    : groups;
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
      complete: group.current >= target,
      display: group.format(group.current),
      rewardIcon: group.rewardIcon,
      rewardLabel: group.rewardLabel,
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

/**
 * A reward the ladder actually pays out. Derived purely from the same tier
 * state `buildSeasonGroups` already computes — nothing is stored separately,
 * so a badge can never disagree with the tier chips beside it.
 */
export interface SeasonBadge {
  /** Matches the owning group's id, e.g. "tend". */
  id: string;
  group: string;
  rewardIcon: string;
  rewardLabel: string;
  /** True once every tier in the group is earned. */
  earned: boolean;
  /** Earned tiers / total tiers, e.g. "2/4". */
  progress: string;
  /** The next tier still to clear, or null once the badge is earned. */
  nextTitle: string | null;
}

/**
 * The trophy shelf: one badge per group, earned when every tier in that
 * group is cleared. Built from `buildSeasonGroups` so the shelf and the
 * ladder can never drift.
 */
export function buildSeasonBadges(
  groups: SeasonGroupProgress[]
): SeasonBadge[] {
  return groups.map((group) => ({
    id: group.id,
    group: group.group,
    rewardIcon: group.rewardIcon,
    rewardLabel: group.rewardLabel,
    earned: group.complete,
    progress: `${group.tiers.filter((tier) => tier.complete).length}/${
      group.tiers.length
    }`,
    nextTitle: group.next?.title ?? null,
  }));
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
