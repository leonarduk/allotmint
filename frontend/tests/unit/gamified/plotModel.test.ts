import { describe, expect, it } from 'vitest';
import {
  buildPlotSnapshot,
  findCropByRouteId,
  germinatingCrops,
  bedIconFor,
  bedNameFor,
  clamp,
  formatGbp,
  formatPct,
  growerRank,
  growthStageFor,
  growthStageMeta,
  levelFromXp,
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
    expect(worst.sellEligible).toBe(false);
    expect(worst.sector).toBe('Unclassified');
  });

  it('returns an empty but usable snapshot with no portfolio', () => {
    const snapshot = buildPlotSnapshot({ portfolio: null });
    expect(snapshot.crops).toEqual([]);
    expect(snapshot.beds).toEqual([]);
    expect(snapshot.plotValueGbp).toBe(0);
    expect(snapshot.grower.level).toBe(1);
    expect(snapshot.resources).toHaveLength(3);
  });
});

describe('resourcesFromPlot', () => {
  const crops = [{ stale: false } as Crop, { stale: true } as Crop];

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
    });
  });

  it('degrades to empty meters when there is nothing to measure', () => {
    const [water, feed, sun] = resourcesFromPlot(null, [], null);
    expect(water).toMatchObject({ pct: 0, display: '0 / 0' });
    expect(feed.hint).toContain('No allowance data');
    expect(sun.pct).toBe(0);
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
    expect(formatPct(null)).toBe('+0.0%');
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

  it('keeps only holdings still serving a minimum holding period', () => {
    const entries = germinatingCrops([
      crop({ ticker: 'READY.L', sellEligible: true, daysUntilEligible: 0 }),
      crop({ ticker: 'UNKNOWN.L', daysUntilEligible: null }),
      crop({ ticker: 'ZERO.L', daysUntilEligible: 0 }),
      crop({ ticker: 'GROWING.L' }),
    ]);
    expect(entries.map((entry) => entry.crop.ticker)).toEqual(['GROWING.L']);
  });

  it('measures progress across the whole holding period', () => {
    const [entry] = germinatingCrops([
      crop({ daysHeld: 10, daysUntilEligible: 20 }),
    ]);
    expect(entry).toMatchObject({
      daysHeld: 10,
      daysRemaining: 20,
      readyOn: '2026-09-13',
    });
    expect(entry.pct).toBeCloseTo(100 / 3);
  });

  it('sorts soonest-ready first and treats an unknown age as day zero', () => {
    const entries = germinatingCrops([
      crop({ ticker: 'LATE.L', daysUntilEligible: 25 }),
      crop({ ticker: 'SOON.L', daysUntilEligible: 2 }),
      crop({ ticker: 'NEW.L', daysHeld: null, daysUntilEligible: 30 }),
    ]);
    expect(entries.map((entry) => entry.crop.ticker)).toEqual([
      'SOON.L',
      'LATE.L',
      'NEW.L',
    ]);
    expect(entries[2]).toMatchObject({ daysHeld: 0, pct: 0 });
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
