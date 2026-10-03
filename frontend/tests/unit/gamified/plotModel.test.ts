import { describe, expect, it } from 'vitest';
import {
  attentionReasonFor,
  buildPlotSnapshot,
  findCropByRouteId,
  germinatingCrops,
  GROWTH_STAGES,
  growthLevelFor,
  bedIconFor,
  bedNameFor,
  clamp,
  compareGainPctDesc,
  formatGbp,
  formatPct,
  growerRank,
  growthStageFor,
  growthStageMeta,
  hasIntradayMove,
  hasVigourSpread,
  isStillInPropagator,
  levelFromXp,
  neediestCrop,
  resourcesFromPlot,
  starsFor,
  vigourFor,
  xpThresholdForLevel,
  type Crop,
} from '@/gamified/plotModel';
import type { Portfolio } from '@/types';

const portfolio: Portfolio = {
  owner: 'steve',
  as_of: '2026-08-24',
  trades_this_month: 3,
  trades_remaining: 7,
  total_value_estimate_gbp: 10_000,
  accounts: [
    {
      account_type: 'stocks-isa',
      currency: 'GBP',
      owner: 'steve',
      value_estimate_gbp: 8_000,
      last_updated: '2026-08-24',
      holdings: [
        {
          ticker: 'VUSA.L',
          name: 'Vanguard S&P 500',
          units: 100,
          market_value_gbp: 8_000,
          effective_cost_basis_gbp: 5_000,
          gain_gbp: 3_000,
          gain_pct: 60,
          day_change_gbp: 80,
          sector: 'Financials',
          region: 'US',
          instrument_type: 'ETF',
          days_held: 400,
          sell_eligible: true,
          last_price_date: '2026-08-24',
        },
      ],
    },
    {
      account_type: 'sipp',
      currency: 'GBP',
      owner: 'steve',
      value_estimate_gbp: 2_000,
      last_updated: '2026-08-20',
      holdings: [
        {
          ticker: 'STALE.L',
          name: 'Neglected Plc',
          units: 10,
          market_value_gbp: 2_000,
          effective_cost_basis_gbp: 3_000,
          gain_gbp: -1_000,
          gain_pct: -33.3,
          day_change_gbp: 0,
          is_stale: true,
          sell_eligible: false,
          days_held: 5,
        },
      ],
    },
  ],
};

describe('growthStageFor', () => {
  it('maps total gain onto the growth ladder', () => {
    expect(growthStageFor(-40)).toBe('wilting');
    expect(growthStageFor(-20)).toBe('wilting');
    expect(growthStageFor(-1)).toBe('seed');
    expect(growthStageFor(0)).toBe('seed');
    expect(growthStageFor(3)).toBe('sprout');
    expect(growthStageFor(12)).toBe('leafing');
    expect(growthStageFor(25)).toBe('budding');
    expect(growthStageFor(45)).toBe('flowering');
    expect(growthStageFor(90)).toBe('fruiting');
    expect(growthStageFor(500)).toBe('bumper');
  });

  it('treats missing or non-finite gain as flat rather than throwing', () => {
    expect(growthStageFor(null)).toBe('seed');
    expect(growthStageFor(undefined)).toBe('seed');
    expect(growthStageFor(Number.NaN)).toBe('seed');
  });
});

describe('growthStageMeta', () => {
  it('returns matching metadata for every stage', () => {
    expect(growthStageMeta('bumper').label).toBe('Bumper crop');
    expect(growthStageMeta('wilting').icon).toBe('🥀');
  });

  it('falls back to a sane stage for an unknown value', () => {
    expect(growthStageMeta('nonsense' as never).id).toBe('seed');
  });
});

describe('starsFor', () => {
  it('awards more stars as a crop takes over the plot', () => {
    expect(starsFor(0.3)).toBe(7);
    expect(starsFor(0.2)).toBe(7);
    expect(starsFor(0.13)).toBe(6);
    expect(starsFor(0.08)).toBe(5);
    expect(starsFor(0.05)).toBe(4);
    expect(starsFor(0.03)).toBe(3);
    expect(starsFor(0.015)).toBe(2);
    expect(starsFor(0.001)).toBe(1);
    expect(starsFor(Number.NaN)).toBe(1);
  });
});

describe('vigourFor', () => {
  it('centres a flat day on 50 and scales with the move', () => {
    expect(vigourFor({ market_value_gbp: 100, day_change_gbp: 0 })).toBe(50);
    expect(vigourFor({ market_value_gbp: 100, day_change_gbp: 5 })).toBe(100);
    expect(vigourFor({ market_value_gbp: 100, day_change_gbp: -5 })).toBe(0);
  });

  it('penalises stale prices and clamps to 0-100', () => {
    expect(
      vigourFor({ market_value_gbp: 100, day_change_gbp: 0, is_stale: true })
    ).toBe(20);
    expect(vigourFor({ market_value_gbp: 100, day_change_gbp: 50 })).toBe(100);
    expect(vigourFor({ market_value_gbp: 0, day_change_gbp: 10 })).toBe(50);
  });
});

describe('hasIntradayMove', () => {
  it('is true only when the backend sent a real day_change_gbp', () => {
    expect(hasIntradayMove({ day_change_gbp: 0 })).toBe(true);
    expect(hasIntradayMove({ day_change_gbp: 12.5 })).toBe(true);
    expect(hasIntradayMove({ day_change_gbp: -3 })).toBe(true);
  });

  it('is false for null/undefined, so "no move recorded" is not read as flat', () => {
    expect(hasIntradayMove({ day_change_gbp: null })).toBe(false);
    expect(hasIntradayMove({ day_change_gbp: undefined })).toBe(false);
  });
});

describe('hasVigourSpread', () => {
  it('is true only when at least two crops carry a real move', () => {
    expect(
      hasVigourSpread([{ hasMove: true }, { hasMove: true }, { hasMove: false }])
    ).toBe(true);
    expect(hasVigourSpread([{ hasMove: true }, { hasMove: false }])).toBe(
      false
    );
    expect(hasVigourSpread([{ hasMove: false }, { hasMove: false }])).toBe(
      false
    );
    expect(hasVigourSpread([])).toBe(false);
  });
});

describe('levelFromXp', () => {
  it('uses the documented 25 * L * (L - 1) curve', () => {
    expect(xpThresholdForLevel(1)).toBe(0);
    expect(xpThresholdForLevel(2)).toBe(50);
    expect(xpThresholdForLevel(3)).toBe(150);
    expect(xpThresholdForLevel(4)).toBe(300);
  });

  it('reports the level and the progress into the next one', () => {
    expect(levelFromXp(0)).toMatchObject({
      level: 1,
      xpIntoLevel: 0,
      xpForLevel: 50,
      pct: 0,
    });
    expect(levelFromXp(49).level).toBe(1);
    expect(levelFromXp(50)).toMatchObject({
      level: 2,
      xpIntoLevel: 0,
      xpForLevel: 100,
    });
    expect(levelFromXp(100)).toMatchObject({
      level: 2,
      xpIntoLevel: 50,
      pct: 50,
    });
    expect(levelFromXp(300).level).toBe(4);
  });

  it('treats missing or negative XP as zero', () => {
    expect(levelFromXp(null).level).toBe(1);
    expect(levelFromXp(undefined).xpTotal).toBe(0);
    expect(levelFromXp(-500).xpTotal).toBe(0);
  });
});

describe('growerRank', () => {
  it('names a rank for each band', () => {
    expect(growerRank(1)).toBe('Seedling Sower');
    expect(growerRank(5)).toBe('Weekend Grower');
    expect(growerRank(10)).toBe('Seasoned Digger');
    expect(growerRank(20)).toBe('Plotholder');
    expect(growerRank(30)).toBe('Master Grower');
    expect(growerRank(50)).toBe('Head Gardener');
  });
});

describe('bed naming', () => {
  it('titles account types and gives each a distinct icon', () => {
    expect(bedNameFor('stocks-isa')).toBe('Stocks Isa');
    expect(bedNameFor('sipp')).toBe('Sipp');
    expect(bedNameFor('   ')).toBe('Unnamed bed');
    expect(bedIconFor('SIPP')).toBe('🌳');
    expect(bedIconFor('mystery-wrapper')).toBe('🌱');
  });
});

describe('buildPlotSnapshot', () => {
  it('turns accounts into beds and holdings into crops sorted by value', () => {
    const snapshot = buildPlotSnapshot({ portfolio, xp: 150, streak: 4 });

    expect(snapshot.owner).toBe('steve');
    expect(snapshot.plotValueGbp).toBe(10_000);
    expect(snapshot.beds.map((bed) => bed.name)).toEqual([
      'Stocks Isa',
      'Sipp',
    ]);
    expect(snapshot.crops.map((crop) => crop.ticker)).toEqual([
      'VUSA.L',
      'STALE.L',
    ]);
    expect(snapshot.totalGainGbp).toBe(2_000);
    expect(snapshot.grower.level).toBe(3);
    expect(snapshot.rank).toBe('Seedling Sower');
    expect(snapshot.streak).toBe(4);
  });

  it('derives stage, stars and bed membership per crop', () => {
    const snapshot = buildPlotSnapshot({ portfolio });
    const [best, worst] = snapshot.crops;

    expect(best.stage).toBe('flowering');
    expect(best.stars).toBe(7);
    expect(best.bedName).toBe('Stocks Isa');
    expect(best.share).toBeCloseTo(0.8);
    expect(best.dayChangePct).toBeCloseTo(1);

    expect(worst.stage).toBe('wilting');
    expect(worst.stale).toBe(true);
    expect(worst.freshness).toBe('stale');
    expect(worst.sellEligible).toBe(false);
    expect(worst.sector).toBe('Unclassified');
  });

  it('treats a holding with no is_stale flag as unknown freshness, not fresh (#7186)', () => {
    // VUSA.L in the shared fixture has a last_price_date but no is_stale
    // flag at all — the backend simply never sent one. That must not be
    // read as a confirmed-fresh price.
    const snapshot = buildPlotSnapshot({ portfolio });
    const vusa = snapshot.crops.find((crop) => crop.ticker === 'VUSA.L');
    expect(vusa?.freshness).toBe('unknown');
    expect(vusa?.stale).toBe(false);
  });

  it('is unknown, not fresh, when is_stale is undefined and last_price_date is null (#7186)', () => {
    // VUSA.L in the shared fixture has a last_price_date but no is_stale
    // flag at all — the backend simply never sent one. That must not be
    // read as a confirmed-fresh price.
    const noFreshnessSignal: Portfolio = {
      owner: 'alex',
      as_of: '2026-08-25',
      trades_this_month: 0,
      trades_remaining: 5,
      total_value_estimate_gbp: 500,
      accounts: [
        {
          account_type: 'gia',
          currency: 'GBP',
          owner: 'alex',
          value_estimate_gbp: 500,
          holdings: [
            {
              ticker: 'HFEL.L',
              name: 'HFEL',
              units: 10,
              market_value_gbp: 500,
              is_stale: undefined,
              last_price_date: null,
            },
          ],
        },
      ],
    };
    const { crops } = buildPlotSnapshot({ portfolio: noFreshnessSignal });
    expect(crops[0].freshness).toBe('unknown');
    expect(crops[0].stale).toBe(false);
    expect(crops[0].lastPriceDate).toBeNull();
  });

  it('is unknown, not stale, when is_stale is explicitly null (the live CASH.GBP shape) (#7186)', () => {
    // The real backend sends `is_stale: null` for cash rows, not just
    // `undefined` — `typeof null === 'object'`, so a naive simplification
    // to `holding.is_stale !== undefined` would silently treat this as a
    // *confirmed* stale price. It must land on 'unknown' like the
    // undefined case above.
    const cashRow: Portfolio = {
      owner: 'alex',
      as_of: '2026-08-25',
      trades_this_month: 0,
      trades_remaining: 5,
      total_value_estimate_gbp: 100,
      accounts: [
        {
          account_type: 'gia',
          currency: 'GBP',
          owner: 'alex',
          value_estimate_gbp: 100,
          holdings: [
            {
              ticker: 'CASH.GBP',
              name: 'Cash (GBP)',
              units: 100,
              market_value_gbp: 100,
              is_stale: null,
              last_price_date: null,
            },
          ],
        },
      ],
    };
    const { crops } = buildPlotSnapshot({ portfolio: cashRow });
    expect(crops[0].freshness).toBe('unknown');
    expect(crops[0].stale).toBe(false);
  });

  it('keeps sell_eligible: null as null instead of coercing it to eligible (#7220 review follow-up)', () => {
    // Regression guard: `holding.sell_eligible !== false` mapped
    // sell_eligible: null (unknown acquisition date) to `true`, silently
    // claiming a holding was eligible when eligibility genuinely could not
    // be determined. Null must stay null.
    const unknownEligibility: Portfolio = {
      owner: 'steve',
      as_of: '2026-08-24',
      trades_this_month: 0,
      trades_remaining: 10,
      total_value_estimate_gbp: 1_000,
      accounts: [
        {
          account_type: 'isa',
          currency: 'GBP',
          owner: 'steve',
          value_estimate_gbp: 1_000,
          last_updated: '2026-08-20',
          holdings: [
            {
              ticker: 'UNKN.L',
              name: 'Unknown Eligibility Plc',
              units: 10,
              market_value_gbp: 1_000,
              acquired_date: null,
              days_held: null,
              sell_eligible: null,
              days_until_eligible: null,
            },
          ],
        },
      ],
    };

    const { crops } = buildPlotSnapshot({ portfolio: unknownEligibility });

    expect(crops[0].sellEligible).toBeNull();
  });

  it('excludes a crop with unknown sell_eligible from the propagator rather than assuming it is still growing (#7220 review follow-up)', () => {
    // isStillInPropagator's authority logic (#7184) is `sellEligible ===
    // false`, not `!sellEligible` -- the latter would coerce
    // sellEligible: null to `true` and put every unknown-eligibility
    // holding in the propagator tray, which on real data (#7220) is most
    // of a portfolio, not the rare confirmed-false case #7184 covers.
    const unknownEligibility: Portfolio = {
      owner: 'steve',
      as_of: '2026-08-24',
      trades_this_month: 0,
      trades_remaining: 10,
      total_value_estimate_gbp: 1_000,
      accounts: [
        {
          account_type: 'isa',
          currency: 'GBP',
          owner: 'steve',
          value_estimate_gbp: 1_000,
          last_updated: '2026-08-20',
          holdings: [
            {
              ticker: 'UNKN.L',
              name: 'Unknown Eligibility Plc',
              units: 10,
              market_value_gbp: 1_000,
              acquired_date: null,
              days_held: null,
              sell_eligible: null,
              days_until_eligible: null,
            },
          ],
        },
      ],
    };

    const { crops } = buildPlotSnapshot({ portfolio: unknownEligibility });

    expect(isStillInPropagator(crops[0])).toBe(false);
  });

  it('marks every crop hasMove: false when the backend sends no intraday move', () => {
    const noMove: Portfolio = {
      owner: 'alex',
      as_of: '2026-08-25',
      trades_this_month: 0,
      trades_remaining: 5,
      total_value_estimate_gbp: 1_000,
      accounts: [
        {
          account_type: 'gia',
          currency: 'GBP',
          owner: 'alex',
          value_estimate_gbp: 1_000,
          holdings: [
            {
              ticker: 'FLAT.L',
              name: 'Flat Plc',
              units: 10,
              market_value_gbp: 500,
              day_change_gbp: null,
            },
            {
              ticker: 'ALSO.L',
              name: 'Also Flat Plc',
              units: 10,
              market_value_gbp: 500,
              day_change_gbp: null,
            },
          ],
        },
      ],
    };
    const { crops } = buildPlotSnapshot({ portfolio: noMove });
    expect(crops.length).toBeGreaterThan(0);
    expect(crops.every((crop) => crop.hasMove === false)).toBe(true);
    // Both crops have no move, so the Vigour sort would be a no-op.
    expect(hasVigourSpread(crops)).toBe(false);
  });

  it('flags hasMove per crop and enables the Vigour sort when a real move exists', () => {
    const withMove: Portfolio = {
      owner: 'alex',
      as_of: '2026-08-25',
      trades_this_month: 0,
      trades_remaining: 5,
      total_value_estimate_gbp: 1_000,
      accounts: [
        {
          account_type: 'gia',
          currency: 'GBP',
          owner: 'alex',
          value_estimate_gbp: 1_000,
          holdings: [
            {
              ticker: 'MOVE.L',
              name: 'Moving Plc',
              units: 10,
              market_value_gbp: 500,
              day_change_gbp: 5,
            },
            {
              ticker: 'STILL.L',
              name: 'Still Plc',
              units: 10,
              market_value_gbp: 500,
              day_change_gbp: -2,
            },
          ],
        },
      ],
    };
    const { crops } = buildPlotSnapshot({ portfolio: withMove });
    expect(crops.every((crop) => crop.hasMove)).toBe(true);
    expect(hasVigourSpread(crops)).toBe(true);
  });

  it('returns an empty but usable snapshot with no portfolio', () => {
    const snapshot = buildPlotSnapshot({ portfolio: null });
    expect(snapshot.crops).toEqual([]);
    expect(snapshot.beds).toEqual([]);
    expect(snapshot.plotValueGbp).toBe(0);
    expect(snapshot.grower.level).toBe(1);
    expect(snapshot.resources).toHaveLength(3);
  });

  it('threads an allowances fetch failure through to the FEED meter hint', () => {
    const snapshot = buildPlotSnapshot({
      portfolio: null,
      allowancesUnavailable: true,
    });
    const feed = snapshot.resources.find((resource) => resource.id === 'feed');
    expect(feed?.hint).toBe('Allowances unavailable right now');
  });
});

describe('resourcesFromPlot', () => {
  const crops = [
    { freshness: 'fresh' } as Crop,
    { freshness: 'stale' } as Crop,
  ];

  it('reads water from trade headroom and sunlight from price freshness', () => {
    const [water, feed, sun] = resourcesFromPlot(
      { trades_this_month: 3, trades_remaining: 7 },
      crops,
      { isa: { used: 4_000, limit: 20_000, remaining: 16_000 } }
    );

    expect(water).toMatchObject({
      current: 7,
      max: 10,
      pct: 70,
      display: '7 / 10',
    });
    // Money resources format their display; counts stay bare.
    expect(feed).toMatchObject({
      current: 16_000,
      max: 20_000,
      pct: 80,
      display: '£16.0k / £20.0k',
    });
    expect(sun).toMatchObject({
      current: 1,
      max: 2,
      pct: 50,
      display: '1 / 2',
      hint: '1 of 2 crops priced from fresh data',
    });
  });

  it('degrades to empty meters when there is nothing to measure', () => {
    const [water, feed, sun] = resourcesFromPlot(null, [], null);
    expect(water).toMatchObject({ pct: 0, display: '0 / 0' });
    expect(feed.hint).toContain('No allowance data');
    expect(sun.pct).toBe(0);
  });

  it('shows a distinct unavailable hint when the allowances fetch failed, not the empty-data copy', () => {
    const [, feed] = resourcesFromPlot(null, [], null, true);
    expect(feed.hint).toBe('Allowances unavailable right now');
    expect(feed.hint).not.toContain('No allowance data');
  });

  it('treats missing is_stale as a third "unknown" state, not fresh (#7186)', () => {
    // Every holding omits `is_stale` and has no `last_price_date` — the
    // exact shape that made SUNLIGHT read 100% before this fix.
    const unknownCrops = [
      { freshness: 'unknown' } as Crop,
      { freshness: 'unknown' } as Crop,
    ];
    const [, , sun] = resourcesFromPlot(null, unknownCrops, null);
    expect(sun.pct).toBe(0);
    expect(sun.current).toBe(0);
    expect(sun.hint).toBe('0 fresh, 2 unknown of 2 crops');
  });

  it('distinguishes fresh, stale and unknown in the caption when all three are present', () => {
    const mixed = [
      { freshness: 'fresh' } as Crop,
      { freshness: 'stale' } as Crop,
      { freshness: 'unknown' } as Crop,
    ];
    const [, , sun] = resourcesFromPlot(null, mixed, null);
    expect(sun.hint).toBe('1 fresh, 1 stale, 1 unknown of 3 crops');
  });
});

describe('formatters', () => {
  it('formats money compactly with a sign', () => {
    expect(formatGbp(5)).toBe('£5.00');
    expect(formatGbp(120)).toBe('£120');
    expect(formatGbp(1_250)).toBe('£1.3k');
    expect(formatGbp(864_100)).toBe('£864.1k');
    expect(formatGbp(5_290_000)).toBe('£5.3m');
    expect(formatGbp(-2_000)).toBe('-£2.0k');
    expect(formatGbp(null)).toBe('£0.00');
  });

  it('always signs percentages', () => {
    expect(formatPct(12.34)).toBe('+12.3%');
    expect(formatPct(-1)).toBe('-1.0%');
  });

  it('renders a missing percentage as a dash, not a confident +0.0% (#8471)', () => {
    expect(formatPct(null)).toBe('—');
    expect(formatPct(undefined)).toBe('—');
    expect(formatPct(Number.NaN)).toBe('—');
    expect(formatPct(0)).toBe('+0.0%');
  });

  it('clamps out-of-range and non-finite values', () => {
    expect(clamp(150, 0, 100)).toBe(100);
    expect(clamp(-5, 0, 100)).toBe(0);
    expect(clamp(Number.NaN, 3, 100)).toBe(3);
  });
});

describe('germinatingCrops', () => {
  const crop = (over: Partial<Crop>): Crop =>
    ({
      ticker: 'X.L',
      sellEligible: false,
      daysHeld: 10,
      daysUntilEligible: 20,
      nextEligibleSellDate: '2026-09-13',
      ...over,
    }) as Crop;

  it('keeps holdings still serving a minimum holding period, including sell_eligible: false alone (#7184)', () => {
    const entries = germinatingCrops([
      crop({ ticker: 'READY.L', sellEligible: true, daysUntilEligible: 0 }),
      // sell_eligible: false with days_until_eligible: null or 0 must still
      // land in the propagator — compliance saying "no" is authoritative,
      // even with no known countdown.
      crop({ ticker: 'UNKNOWN.L', daysUntilEligible: null }),
      crop({ ticker: 'ZERO.L', daysUntilEligible: 0 }),
      crop({ ticker: 'GROWING.L' }),
    ]);
    expect(entries.map((entry) => entry.crop.ticker)).toEqual([
      'GROWING.L',
      'UNKNOWN.L',
      'ZERO.L',
    ]);
  });

  it('measures progress across the whole holding period when the countdown is known', () => {
    const [entry] = germinatingCrops([
      crop({ daysHeld: 10, daysUntilEligible: 20 }),
    ]);
    expect(entry).toMatchObject({
      daysHeld: 10,
      daysRemaining: 20,
      readyOn: '2026-09-13',
      indeterminate: false,
    });
    expect(entry.pct).toBeCloseTo(100 / 3);
  });

  it('reports an indeterminate, empty-bar entry when there is no known countdown (#7184)', () => {
    const [entry] = germinatingCrops([
      crop({
        ticker: 'ZERO.L',
        daysHeld: 364,
        daysUntilEligible: 0,
        nextEligibleSellDate: '2025-09-25',
      }),
    ]);
    // A 100%-full bar here would read as "about to clear" — the opposite of
    // what sell_eligible: false means, however many days have been held.
    expect(entry).toMatchObject({
      pct: 0,
      daysRemaining: 0,
      readyOn: null,
      indeterminate: true,
    });
  });

  it('excludes a sell_eligible: true holding even with a stale positive countdown attached (#7184)', () => {
    // sell_eligible is authoritative in both directions — a holding
    // compliance says is freely sellable must never show up here, no
    // matter what days_until_eligible still says.
    const entries = germinatingCrops([
      crop({ ticker: 'FREE.L', sellEligible: true, daysUntilEligible: 5 }),
    ]);
    expect(entries).toEqual([]);
  });

  it('sorts soonest-ready first, treats an unknown age as day zero, and trails indeterminate entries', () => {
    const entries = germinatingCrops([
      crop({ ticker: 'LATE.L', daysUntilEligible: 25 }),
      crop({ ticker: 'SOON.L', daysUntilEligible: 2 }),
      crop({ ticker: 'NEW.L', daysHeld: null, daysUntilEligible: 30 }),
      crop({ ticker: 'STUCK.L', daysUntilEligible: null }),
    ]);
    expect(entries.map((entry) => entry.crop.ticker)).toEqual([
      'SOON.L',
      'LATE.L',
      'NEW.L',
      'STUCK.L',
    ]);
    expect(entries[2]).toMatchObject({ daysHeld: 0, pct: 0 });
  });
});

describe('isStillInPropagator', () => {
  const crop = (over: Partial<Crop>): Crop =>
    ({
      ticker: 'X.L',
      sellEligible: false,
      daysHeld: 10,
      daysUntilEligible: 20,
      nextEligibleSellDate: '2026-09-13',
      ...over,
    }) as Crop;

  it('is the single check both the hub widget and crop detail rely on (#7010, #7184)', () => {
    // Already eligible and no positive countdown — nothing left to hold it
    // back, so it has cleared the propagator.
    expect(
      isStillInPropagator(crop({ sellEligible: true, daysUntilEligible: 0 }))
    ).toBe(false);
    // sell_eligible: false is authoritative on its own — it must never be
    // overridden by days_until_eligible reporting 0 or being absent, which
    // is exactly the HFEL.L / JEGI.L / SERE.L shape from the alex fixture.
    expect(isStillInPropagator(crop({ daysUntilEligible: 0 }))).toBe(true);
    expect(isStillInPropagator(crop({ daysUntilEligible: -3 }))).toBe(true);
    expect(isStillInPropagator(crop({ daysUntilEligible: null }))).toBe(true);
    // Still serving the minimum holding period.
    expect(isStillInPropagator(crop({ daysUntilEligible: 5 }))).toBe(true);
    // sell_eligible: true is *also* authoritative on its own, even with a
    // stale, not-yet-cleared days_until_eligible still attached (e.g. the
    // backend recalculated eligibility before refreshing the countdown).
    // #7184's own "Failure looks like" section names the alternative —
    // "the fix inverts the bug and puts freely sellable crops in the
    // propagator" — as a failure, so an OR-style "either signal puts it in
    // the propagator" reading is rejected here even though the issue's
    // prose elsewhere describes the countdown as "an additional reason".
    expect(
      isStillInPropagator(crop({ sellEligible: true, daysUntilEligible: 5 }))
    ).toBe(false);
  });
});

describe('crop identity', () => {
  // The repo's own demo accounts hold VWRL.L twice in one ISA and again in
  // the SIPP, which is exactly what a ticker-keyed list collides on.
  const repeated: Portfolio = {
    owner: 'steve',
    as_of: '2026-08-24',
    trades_this_month: 0,
    trades_remaining: 10,
    total_value_estimate_gbp: 300,
    accounts: [
      {
        account_type: 'stocks-isa',
        currency: 'GBP',
        owner: 'steve',
        value_estimate_gbp: 200,
        holdings: [
          {
            ticker: 'VWRL.L',
            name: 'Vanguard All-World',
            units: 1,
            market_value_gbp: 100,
          },
          {
            ticker: 'VWRL.L',
            name: 'Vanguard All-World',
            units: 2,
            market_value_gbp: 100,
          },
        ],
      },
      {
        account_type: 'sipp',
        currency: 'GBP',
        owner: 'steve',
        value_estimate_gbp: 100,
        holdings: [
          {
            ticker: 'VWRL.L',
            name: 'Vanguard All-World',
            units: 3,
            market_value_gbp: 100,
          },
        ],
      },
    ],
  };

  it('gives every holding row its own id even when tickers repeat', () => {
    const { crops } = buildPlotSnapshot({ portfolio: repeated });
    expect(crops).toHaveLength(3);
    expect(new Set(crops.map((crop) => crop.id)).size).toBe(3);
    // All three share a ticker, which is why the id cannot be derived from it.
    expect(new Set(crops.map((crop) => crop.ticker)).size).toBe(1);
  });

  it('keeps ids stable for the same payload', () => {
    const first = buildPlotSnapshot({ portfolio: repeated }).crops.map(
      (c) => c.id
    );
    const second = buildPlotSnapshot({ portfolio: repeated }).crops.map(
      (c) => c.id
    );
    expect(first).toEqual(second);
  });

  it('resolves a route id, falling back to a bare ticker', () => {
    const { crops } = buildPlotSnapshot({ portfolio: repeated });
    const second = crops[1];

    expect(findCropByRouteId(crops, second.id)).toBe(second);
    // A bare ticker still lands somewhere sensible for older/bookmarked links.
    expect(findCropByRouteId(crops, 'VWRL.L')?.ticker).toBe('VWRL.L');
    expect(findCropByRouteId(crops, 'NOPE.L')).toBeUndefined();
  });
});

describe('unknown cost basis (#8471)', () => {
  const plotWith = (holding: Portfolio['accounts'][number]['holdings'][number]) =>
    buildPlotSnapshot({
      portfolio: {
        owner: 'steve',
        as_of: '2026-08-24',
        total_value_estimate_gbp: 2_000,
        accounts: [
          {
            account_type: 'isa',
            currency: 'GBP',
            value_estimate_gbp: 2_000,
            holdings: [holding],
          },
        ],
      } as Portfolio,
    });

  it('keeps gain null, not 0 or the market value, when cost is zero', () => {
    const { crops, totalGainGbp } = plotWith({
      ticker: 'ZERO.L',
      name: 'Zero Cost',
      units: 10,
      market_value_gbp: 1_000,
      cost_basis_gbp: 0,
      effective_cost_basis_gbp: 0,
      gain_gbp: null,
      gain_pct: null,
    });

    expect(crops[0].gainGbp).toBeNull();
    expect(crops[0].gainPct).toBeNull();
    expect(totalGainGbp).toBe(0);
  });

  it('keeps gain null for a last-resort guessed cost', () => {
    const { crops } = plotWith({
      ticker: 'GUESS.L',
      name: 'Guessed Cost',
      units: 10,
      market_value_gbp: 1_000,
      effective_cost_basis_gbp: 1_000,
      gain_gbp: 0,
      gain_pct: 0,
      cost_basis_source: 'unknown',
    });

    expect(crops[0].gainGbp).toBeNull();
    expect(crops[0].gainPct).toBeNull();
  });

  it('still derives gain from a real cost when the backend omits it', () => {
    const { crops } = plotWith({
      ticker: 'REAL.L',
      name: 'Real Cost',
      units: 10,
      market_value_gbp: 1_200,
      effective_cost_basis_gbp: 1_000,
    });

    expect(crops[0].gainGbp).toBe(200);
    expect(crops[0].gainPct).toBe(20);
  });

  it('never flags an unknown gain as a loss and sorts it last', () => {
    const unknown = { ticker: 'U', gainPct: null, freshness: 'fresh', sellEligible: true } as Crop;
    const up = { ...unknown, ticker: 'UP', gainPct: 5 } as Crop;
    const down = { ...unknown, ticker: 'DOWN', gainPct: -10 } as Crop;

    expect(attentionReasonFor(unknown)).toBeNull();
    expect([unknown, down, up].sort(compareGainPctDesc).map((c) => c.ticker)).toEqual([
      'UP',
      'DOWN',
      'U',
    ]);
  });
});

describe('attentionReasonFor', () => {
  const crop = (over: Partial<Crop>): Crop =>
    ({
      ticker: 'X.L',
      gainPct: 0,
      freshness: 'fresh',
      sellEligible: true,
      ...over,
    }) as Crop;

  it('returns null for a healthy crop, however it ranks', () => {
    // A crop that is merely the least-up on a green plot is not a problem.
    expect(attentionReasonFor(crop({ gainPct: 5 }))).toBeNull();
    expect(attentionReasonFor(crop({ gainPct: 0 }))).toBeNull();
    expect(attentionReasonFor(crop({ gainPct: -4.9 }))).toBeNull();
  });

  it('flags a real loss with the amount stated', () => {
    expect(attentionReasonFor(crop({ gainPct: -9.5 }))).toEqual({
      label: 'down 9.5%',
      kind: 'loss',
    });
    expect(attentionReasonFor(crop({ gainPct: -5 }))?.kind).toBe('loss');
  });

  it('flags a stale price', () => {
    expect(attentionReasonFor(crop({ freshness: 'stale' }))).toEqual({
      label: 'price is stale',
      kind: 'stale-price',
    });
  });

  it('flags a compliance block', () => {
    expect(attentionReasonFor(crop({ sellEligible: false }))).toEqual({
      label: 'not sellable yet',
      kind: 'not-sellable',
    });
  });

  it('picks the most actionable problem, not just the worst gain', () => {
    // A -40% loss that is also not sellable reports the compliance block:
    // "you cannot sell this" is more actionable than "this is down".
    expect(
      attentionReasonFor(crop({ gainPct: -40, sellEligible: false }))?.kind
    ).toBe('not-sellable');
    // A stale price beats a loss for the same reason.
    expect(
      attentionReasonFor(crop({ gainPct: -40, freshness: 'stale' }))?.kind
    ).toBe('stale-price');
  });
});

describe('neediestCrop', () => {
  const crop = (over: Partial<Crop>): Crop =>
    ({
      ticker: 'X.L',
      gainPct: 0,
      freshness: 'fresh',
      sellEligible: true,
      ...over,
    }) as Crop;

  it('returns undefined when nothing is actually wrong', () => {
    expect(
      neediestCrop([crop({ ticker: 'A', gainPct: 5 }), crop({ ticker: 'B', gainPct: 1 })])
    ).toBeUndefined();
    expect(neediestCrop([])).toBeUndefined();
  });

  it('picks the worst offender by the same priority the reason uses', () => {
    const picked = neediestCrop([
      crop({ ticker: 'LOSS', gainPct: -20 }),
      crop({ ticker: 'STALE', freshness: 'stale' }),
      crop({ ticker: 'BLOCKED', sellEligible: false }),
    ]);
    expect(picked?.ticker).toBe('BLOCKED');
  });

  it('breaks ties within a kind by the worst gain', () => {
    const picked = neediestCrop([
      crop({ ticker: 'MILD', gainPct: -6 }),
      crop({ ticker: 'DEEP', gainPct: -30 }),
    ]);
    expect(picked?.ticker).toBe('DEEP');
  });
});

describe('growthLevelFor', () => {
  it('gives every stage a level, worst to best', () => {
    expect(GROWTH_STAGES.map((stage) => growthLevelFor(stage.id))).toEqual([
      0, 0, 1, 1, 2, 3, 4, 5,
    ]);
  });

  it('agrees with the stage chip on every band boundary', () => {
    // The two ladders used to disagree here: growthStageFor bands with `<=`,
    // so a crop on exactly 120% is fruiting, while a separate `>=` ladder
    // called the same crop bumper — chip and trait level contradicted.
    for (const boundary of [-20, 0, 5, 15, 30, 60, 120]) {
      const stage = growthStageFor(boundary);
      expect(growthLevelFor(stage)).toBe(
        growthLevelFor(growthStageFor(boundary))
      );
    }
    expect(growthLevelFor(growthStageFor(120))).toBe(4); // fruiting, not bumper
    expect(growthLevelFor(growthStageFor(120.1))).toBe(5);
    expect(growthLevelFor(growthStageFor(60))).toBe(3); // flowering
    expect(growthLevelFor(growthStageFor(15))).toBe(1); // leafing
    expect(growthLevelFor(growthStageFor(-40))).toBe(0); // wilting
  });
});
