import { describe, expect, it } from 'vitest';
import {
  bedGain,
  bedWrapperExplanation,
  instrumentTypeExplanation,
  nextPlotJob,
  plotJobs,
  type PlotJobInput,
} from '@/gamified/plotGuidance';
import { buildPlotSnapshot, type Crop } from '@/gamified/plotModel';
import type { Holding, Portfolio } from '@/types';

function holding(overrides: Partial<Holding>): Holding {
  return {
    ticker: 'AAA.L',
    name: 'AAA plc',
    units: 1,
    market_value_gbp: 1_000,
    effective_cost_basis_gbp: 1_000,
    gain_gbp: 0,
    gain_pct: 0,
    sector: 'Industrials',
    region: 'UK',
    instrument_type: 'Equity',
    days_held: 400,
    sell_eligible: true,
    ...overrides,
  } as Holding;
}

function crops(accounts: Portfolio['accounts']): Crop[] {
  return buildPlotSnapshot({
    portfolio: {
      owner: 'steve',
      as_of: '2026-08-24',
      trades_this_month: 0,
      trades_remaining: 10,
      total_value_estimate_gbp: 10_000,
      accounts,
    },
  }).crops;
}

function input(overrides: Partial<PlotJobInput> = {}): PlotJobInput {
  return {
    // A Monday, priced the same day: fresh.
    asOf: '2026-08-24',
    today: '2026-08-24',
    crops: [],
    cashGbp: 0,
    plotValueGbp: 10_000,
    allowances: null,
    openChores: 0,
    basePath: '/plot',
    ...overrides,
  };
}

describe('nextPlotJob (#7209)', () => {
  it('says nothing needs doing rather than inventing a nudge', () => {
    expect(nextPlotJob(input())).toBeNull();
    expect(plotJobs(input())).toEqual([]);
  });

  it('puts stale prices first, linking to data quality', () => {
    const job = nextPlotJob(
      input({ asOf: '2026-08-07', today: '2026-08-24', openChores: 2 })
    );
    expect(job?.kind).toBe('stale-prices');
    expect(job?.title).toBe('Prices are 17 days old');
    expect(job?.to).toBe('/data-quality');
  });

  it('names holdings blocked on approval, ahead of chores', () => {
    const plot = crops([
      {
        account_type: 'isa',
        holdings: [
          holding({
            ticker: 'BBB.L',
            sell_eligible: false,
            sell_block_reason: 'needs_approval',
          }),
        ],
      },
    ] as Portfolio['accounts']);
    const job = nextPlotJob(input({ crops: plot, openChores: 1 }));
    expect(job?.kind).toBe('needs-approval');
    expect(job?.title).toBe('1 holding needs sign-off before it can be sold');
    expect(job?.reason).toMatch(/^BBB\.L:/);
    expect(job?.to).toBe('/trade-compliance');
  });

  it('points open chores at the chores screen', () => {
    const job = nextPlotJob(input({ openChores: 2 }));
    expect(job).toMatchObject({
      kind: 'open-chores',
      title: '2 chores still open today',
      to: '/plot/chores',
    });
  });

  it('reports unused ISA allowance as a fact with the real figures', () => {
    const job = nextPlotJob(
      input({
        allowances: { isa: { used: 2_600, limit: 20_000, remaining: 17_400 } },
      })
    );
    expect(job?.kind).toBe('isa-headroom');
    expect(job?.title).toBe(
      '£17.4k of your £20.0k ISA allowance is unused this tax year'
    );
    expect(job?.to).toBe('/tax-tools');
  });

  it('ignores a used-up or missing ISA allowance', () => {
    expect(
      nextPlotJob(
        input({ allowances: { isa: { used: 20_000, limit: 20_000, remaining: 0 } } })
      )
    ).toBeNull();
    expect(
      nextPlotJob(
        input({ allowances: { pension: { used: 0, limit: 60_000, remaining: 60_000 } } })
      )
    ).toBeNull();
  });

  it('mentions cash only when it is a meaningful share of the plot', () => {
    expect(nextPlotJob(input({ cashGbp: 400 }))).toBeNull();
    const job = nextPlotJob(input({ cashGbp: 1_740, plotValueGbp: 10_000 }));
    expect(job?.kind).toBe('uninvested-cash');
    expect(job?.title).toBe('£1.7k (17% of your plot) is held as cash');
    expect(job?.to).toBe('/allocation');
  });

  it('notes an instrument held in more than one bed, linking to the crop', () => {
    const plot = crops([
      { account_type: 'isa', holdings: [holding({ ticker: 'ERNS.L' })] },
      {
        account_type: 'sipp',
        holdings: [holding({ ticker: 'ERNS.L', market_value_gbp: 500 })],
      },
    ] as Portfolio['accounts']);
    const job = nextPlotJob(input({ crops: plot }));
    expect(job?.kind).toBe('split-holding');
    expect(job?.title).toBe('You hold ERNS.L in 2 accounts');
    expect(job?.reason).toContain('Isa, Sipp');
    expect(job?.to).toBe(`/plot/crops/${encodeURIComponent(plot[0].id)}`);
  });

  it('never phrases a job as a buy or sell instruction', () => {
    const jobs = plotJobs(
      input({
        asOf: '2026-08-07',
        openChores: 1,
        cashGbp: 5_000,
        allowances: { isa: { used: 0, limit: 20_000, remaining: 20_000 } },
      })
    );
    expect(jobs.length).toBeGreaterThan(1);
    for (const job of jobs) {
      expect(`${job.title} ${job.reason}`).not.toMatch(/\b(buy|sell now|invest in)\b/i);
    }
  });
});

describe('plain-English explanations (#7209)', () => {
  it('explains instrument types regardless of casing', () => {
    expect(instrumentTypeExplanation('ETF')).toMatch(/^An exchange-traded fund/);
    expect(instrumentTypeExplanation('etf')).toMatch(/^An exchange-traded fund/);
    expect(instrumentTypeExplanation('Bond')).toMatch(/^A bond: a loan/);
    expect(instrumentTypeExplanation('Investment Trust')).toMatch(
      /^An investment trust/
    );
  });

  it('admits when it does not know the type', () => {
    expect(instrumentTypeExplanation('Unknown')).toBe(
      'The data does not say what kind of investment this is.'
    );
    expect(instrumentTypeExplanation(null)).toBe(
      'The data does not say what kind of investment this is.'
    );
  });

  it('explains each bed wrapper', () => {
    expect(bedWrapperExplanation('stocks-isa')).toMatch(/^An ISA/);
    expect(bedWrapperExplanation('SIPP')).toMatch(/^A pension/);
    expect(bedWrapperExplanation('gia')).toMatch(/^A general investment account/);
    expect(bedWrapperExplanation('mystery')).toBe(
      'The type of account is not recorded.'
    );
  });
});

describe('bedGain (#7209)', () => {
  it('sums gain and cost across the crops in one bed', () => {
    const plot = crops([
      {
        account_type: 'isa',
        holdings: [
          holding({ ticker: 'A', gain_gbp: 300, effective_cost_basis_gbp: 1_000 }),
          holding({ ticker: 'B', gain_gbp: -100, effective_cost_basis_gbp: 1_000 }),
        ],
      },
      { account_type: 'gia', holdings: [holding({ ticker: 'C', gain_gbp: 50 })] },
    ] as Portfolio['accounts']);
    const gain = bedGain({ id: plot[0].bedId }, plot);
    expect(gain.gainGbp).toBe(200);
    expect(gain.gainPct).toBeCloseTo(10);
  });

  it('is unknown, not zero, when a cost basis is unreliable or the bed is empty', () => {
    const plot = crops([
      {
        account_type: 'isa',
        holdings: [holding({ ticker: 'A', cost_basis_source: 'unknown' })],
      },
    ] as Portfolio['accounts']);
    expect(bedGain({ id: plot[0].bedId }, plot)).toEqual({
      gainGbp: null,
      gainPct: null,
    });
    expect(bedGain({ id: 'nobody:isa' }, plot)).toEqual({
      gainGbp: null,
      gainPct: null,
    });
  });
});
