import { describe, expect, it } from 'vitest';
import {
  buildSeasonGoals,
  buildSeasonGroups,
  buildStreakPath,
  parseTaxYear,
  seasonCountdown,
} from '@/gamified/seasonModel';
import { buildPlotSnapshot } from '@/gamified/plotModel';
import type { Portfolio } from '@/types';

const portfolio: Portfolio = {
  owner: 'steve',
  as_of: '2026-08-24',
  trades_this_month: 3,
  trades_remaining: 7,
  total_value_estimate_gbp: 60_000,
  accounts: [
    {
      account_type: 'stocks-isa',
      currency: 'GBP',
      owner: 'steve',
      value_estimate_gbp: 60_000,
      holdings: [
        {
          ticker: 'A.L',
          name: 'A',
          units: 1,
          market_value_gbp: 30_000,
          effective_cost_basis_gbp: 20_000,
          gain_gbp: 10_000,
          gain_pct: 50,
        },
        {
          ticker: 'B.L',
          name: 'B',
          units: 1,
          market_value_gbp: 30_000,
          effective_cost_basis_gbp: 20_000,
          gain_gbp: 10_000,
          gain_pct: 50,
        },
      ],
    },
  ],
};

describe('parseTaxYear', () => {
  it('turns the backend "YYYY-YYYY" form into a season ending 5 April', () => {
    expect(parseTaxYear('2026-2027')).toEqual({
      label: '2026/27',
      endsOn: '2027-04-05',
    });
    expect(parseTaxYear(' 2030-2031 ')).toEqual({
      label: '2030/31',
      endsOn: '2031-04-05',
    });
  });

  it('rejects anything that is not a consecutive year pair', () => {
    expect(parseTaxYear('2026/27')).toBeNull();
    expect(parseTaxYear('2026-2028')).toBeNull();
    expect(parseTaxYear('nonsense')).toBeNull();
    expect(parseTaxYear(null)).toBeNull();
    expect(parseTaxYear(undefined)).toBeNull();
  });
});

describe('seasonCountdown', () => {
  const season = { label: '2026/27', endsOn: '2027-04-05' };

  it('counts whole days and hours to the end of 5 April', () => {
    // The tax year ends at the close of 5 April, so midday on the 4th still
    // has a day and a half to run.
    const countdown = seasonCountdown(season, new Date('2027-04-04T12:00:00Z'));
    expect(countdown).toMatchObject({ days: 1, hours: 12, expired: false });
    expect(countdown.label).toBe('Ends in 1 day and 12 hours');
  });

  it('drops the day part on the final day', () => {
    const countdown = seasonCountdown(season, new Date('2027-04-05T18:00:00Z'));
    expect(countdown).toMatchObject({ days: 0, hours: 6, expired: false });
    expect(countdown.label).toBe('Ends in 6 hours');
  });

  it('reports a closed season once 5 April has passed', () => {
    const countdown = seasonCountdown(season, new Date('2027-04-06T00:00:00Z'));
    expect(countdown).toMatchObject({ days: 0, hours: 0, expired: true });
    expect(countdown.label).toBe('Season closed');
  });

  it('handles a mid-season date without going negative', () => {
    const countdown = seasonCountdown(season, new Date('2026-08-24T10:00:00Z'));
    expect(countdown.expired).toBe(false);
    expect(countdown.days).toBeGreaterThan(200);
  });
});

describe('buildSeasonGoals', () => {
  const snapshot = buildPlotSnapshot({ portfolio, xp: 300, streak: 6 });
  const goals = buildSeasonGoals(snapshot, {
    isa: { used: 4_200, limit: 20_000, remaining: 15_800 },
    pension: { used: 9_000, limit: 60_000, remaining: 51_000 },
  });

  it('emits one row per tier across all five groups', () => {
    expect(goals).toHaveLength(20);
    expect(new Set(goals.map((goal) => goal.group)).size).toBe(5);
    expect(new Set(goals.map((goal) => goal.id)).size).toBe(20);
  });

  it('marks a tier complete once the real figure clears it', () => {
    const tend5 = goals.find((goal) => goal.id === 'tend-5');
    const tend10 = goals.find((goal) => goal.id === 'tend-10');
    // Two holdings: neither crop tier is cleared.
    expect(tend5).toMatchObject({ current: 2, complete: false, pct: 40 });
    expect(tend10?.complete).toBe(false);

    const grow50k = goals.find((goal) => goal.id === 'grow-50000');
    expect(grow50k).toMatchObject({
      current: 60_000,
      complete: true,
      pct: 100,
    });
  });

  it('sums allowance usage across every allowance row', () => {
    const feed10k = goals.find((goal) => goal.id === 'feed-10000');
    expect(feed10k).toMatchObject({ current: 13_200, complete: true });
    expect(feed10k?.display).toBe('£13.2k');
  });

  it('shows the true current figure on a cleared tier, not the target', () => {
    const streak3 = goals.find((goal) => goal.id === 'streak-3');
    expect(streak3).toMatchObject({ complete: true, display: '6 days' });
  });

  it('reads level from the grower curve', () => {
    // 300 XP is exactly level 4 on the 25 * L * (L - 1) curve.
    const rank4 = goals.find((goal) => goal.id === 'rank-4');
    expect(rank4).toMatchObject({ current: 4, complete: true });
    expect(goals.find((goal) => goal.id === 'rank-8')?.complete).toBe(false);
  });

  it('treats missing allowances as zero usage rather than throwing', () => {
    const withoutAllowances = buildSeasonGoals(snapshot, null);
    expect(
      withoutAllowances.filter((goal) => goal.id.startsWith('feed-'))
    ).toHaveLength(4);
    expect(
      withoutAllowances.find((goal) => goal.id === 'feed-1000')
    ).toMatchObject({ current: 0, complete: false, pct: 0 });
  });

  it('marks only the "Feed the beds" tiers unavailable when the allowances fetch failed', () => {
    const failed = buildSeasonGoals(snapshot, null, true);
    const feedGoals = failed.filter((goal) => goal.id.startsWith('feed-'));
    expect(feedGoals).toHaveLength(4);
    for (const goal of feedGoals) {
      expect(goal.unavailable).toBe(true);
      expect(goal.complete).toBe(false);
      expect(goal.display).toBe('Allowances unavailable right now');
    }
    // Other groups are unaffected by an allowances failure.
    const nonFeedGoals = failed.filter((goal) => !goal.id.startsWith('feed-'));
    expect(nonFeedGoals.every((goal) => !goal.unavailable)).toBe(true);
  });
});

describe('buildSeasonGroups', () => {
  const snapshot = buildPlotSnapshot({ portfolio, xp: 300, streak: 6 });
  const groups = buildSeasonGroups(snapshot, {
    isa: { used: 4_200, limit: 20_000, remaining: 15_800 },
    pension: { used: 9_000, limit: 60_000, remaining: 51_000 },
  });

  it('emits one row per category, not per tier', () => {
    expect(groups).toHaveLength(5);
    expect(groups.map((group) => group.group)).toEqual([
      'Tend the plot',
      'Grow the plot',
      'Feed the beds',
      'Keep the streak',
      'Earn your rank',
    ]);
  });

  it('tracks progress toward the first tier not yet earned, not the last', () => {
    // Plot value is £60k: the £1k/£10k/£50k tiers are cleared, £250k is next.
    const grow = groups.find((group) => group.id === 'grow');
    expect(grow?.currentDisplay).toBe('£60.0k');
    expect(grow?.next).toMatchObject({
      target: 250_000,
      displayTarget: '£250.0k',
    });
    expect(grow?.next?.pct).toBeCloseTo(24, 0);
    expect(grow?.complete).toBe(false);
  });

  it('marks a category complete only once every tier is cleared', () => {
    // Allowance usage is £13.2k: clears 1k/5k/10k but not the 20k tier.
    const feed = groups.find((group) => group.id === 'feed');
    expect(feed?.next).toMatchObject({ target: 20_000 });
    expect(feed?.complete).toBe(false);
    expect(
      feed?.tiers.filter((tier) => tier.complete).map((tier) => tier.target)
    ).toEqual([1_000, 5_000, 10_000]);

    // Two holdings never reach the 5-crop tier.
    const tend = groups.find((group) => group.id === 'tend');
    expect(tend?.next).toMatchObject({ target: 5 });
  });

  it('reports no next tier once a category is fully earned', () => {
    // A grower with a very large plot clears every "grow" tier.
    const richSnapshot = buildPlotSnapshot({
      portfolio: { ...portfolio, total_value_estimate_gbp: 999_999 },
      xp: 300,
      streak: 6,
    });
    const richGroups = buildSeasonGroups(richSnapshot, null);
    const grow = richGroups.find((group) => group.id === 'grow');
    expect(grow?.next).toBeNull();
    expect(grow?.complete).toBe(true);
    expect(grow?.tiers.every((tier) => tier.complete)).toBe(true);
  });
});

describe('buildStreakPath', () => {
  it('builds the last seven days ending on today, oldest first', () => {
    const days = buildStreakPath({}, '2026-08-24');
    expect(days).toHaveLength(7);
    expect(days[0].date).toBe('2026-08-18');
    expect(days[6].date).toBe('2026-08-24');
    expect(days[6].isToday).toBe(true);
    expect(days[0].isToday).toBe(false);
    // 18 Aug 2026 is a Tuesday, 24 Aug a Monday.
    expect(days.map((day) => day.initial)).toEqual([
      'T',
      'W',
      'T',
      'F',
      'S',
      'S',
      'M',
    ]);
  });

  it('stamps a day only when every daily chore was finished', () => {
    const days = buildStreakPath(
      {
        '2026-08-23': { completed: 2, total: 2 },
        '2026-08-24': { completed: 1, total: 2 },
      },
      '2026-08-24'
    );
    const [, ...recent] = days;
    const yesterday = recent.find((day) => day.date === '2026-08-23');
    const today = recent.find((day) => day.date === '2026-08-24');

    expect(yesterday).toMatchObject({ stamped: true, partial: false });
    expect(today).toMatchObject({
      stamped: false,
      partial: true,
      completed: 1,
    });
  });

  it('leaves days the backend has no record for blank', () => {
    const days = buildStreakPath(null, '2026-08-24');
    expect(days.every((day) => !day.stamped && !day.partial)).toBe(true);
    expect(days.every((day) => day.total === 0)).toBe(true);
  });

  it('honours a custom length and returns nothing for an unparseable date', () => {
    expect(buildStreakPath({}, '2026-08-24', 3)).toHaveLength(3);
    expect(buildStreakPath({}, 'not-a-date')).toEqual([]);
  });
});
