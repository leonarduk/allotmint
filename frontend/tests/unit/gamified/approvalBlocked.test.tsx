import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import Propagator from '@/gamified/components/Propagator';
import {
  awaitingApprovalCrops,
  buildPlotSnapshot,
  germinatingCrops,
  isAwaitingApproval,
  isStillInPropagator,
  type Crop,
} from '@/gamified/plotModel';
import type { Portfolio } from '@/types';

// #10812: a holding past its minimum hold but blocked on approval is
// sell_eligible: false with no countdown. It must read "Needs approval",
// not "Not yet liftable", and stay out of the propagator's hold-period count.

const crop = (over: Partial<Crop>): Crop =>
  ({
    id: over.ticker ?? 'X.L',
    ticker: 'X.L',
    sector: 'Energy',
    stage: 'sprout',
    sellEligible: false,
    sellBlockReason: 'hold_period',
    daysHeld: 6,
    daysUntilEligible: 24,
    nextEligibleSellDate: '2026-11-06',
    ...over,
  }) as Crop;

const approvalBlocked = crop({
  ticker: 'BP.L',
  sellBlockReason: 'needs_approval',
  daysHeld: 524,
  daysUntilEligible: null,
  nextEligibleSellDate: '2025-06-06',
});
const holdPeriod = crop({ ticker: 'ZPRX.DE' });

describe('approval-blocked crops (#10812)', () => {
  it('maps sell_block_reason from the holding, ignoring unknown values', () => {
    const portfolio: Portfolio = {
      owner: 'steve',
      as_of: '2026-10-13',
      trades_this_month: 0,
      trades_remaining: 10,
      total_value_estimate_gbp: 300,
      accounts: [
        {
          account_type: 'isa',
          currency: 'GBP',
          value_estimate_gbp: 300,
          holdings: [
            {
              ticker: 'BP.L',
              units: 1,
              market_value_gbp: 100,
              sell_eligible: false,
              sell_block_reason: 'needs_approval',
            },
            {
              ticker: 'ZPRX.DE',
              units: 1,
              market_value_gbp: 100,
              sell_eligible: false,
              sell_block_reason: 'hold_period',
            },
            {
              ticker: 'ODD.L',
              units: 1,
              market_value_gbp: 100,
              sell_eligible: false,
              sell_block_reason: 'something_new',
            },
          ],
        },
      ],
    };
    const { crops } = buildPlotSnapshot({ portfolio });
    const byTicker = Object.fromEntries(
      crops.map((c) => [c.ticker, c.sellBlockReason])
    );
    expect(byTicker).toEqual({
      'BP.L': 'needs_approval',
      'ZPRX.DE': 'hold_period',
      'ODD.L': null,
    });
  });

  it('keeps approval-blocked crops out of the propagator and lists them separately', () => {
    const legacy = crop({
      ticker: 'OLD.L',
      sellBlockReason: null,
      daysUntilEligible: null,
    });
    const sellable = crop({
      ticker: 'FREE.L',
      sellEligible: true,
      sellBlockReason: null,
    });
    const crops = [approvalBlocked, holdPeriod, legacy, sellable];

    expect(isStillInPropagator(approvalBlocked)).toBe(false);
    expect(isAwaitingApproval(approvalBlocked)).toBe(true);
    expect(isAwaitingApproval(holdPeriod)).toBe(false);
    // A false with no reason (older payload) still counts as hold period.
    expect(isStillInPropagator(legacy)).toBe(true);

    expect(germinatingCrops(crops).map((entry) => entry.crop.ticker)).toEqual([
      'ZPRX.DE',
      'OLD.L',
    ]);
    expect(awaitingApprovalCrops(crops).map((c) => c.ticker)).toEqual(['BP.L']);
  });

  it('labels approval-blocked crops "Needs approval" with a Trading Rules link', () => {
    render(
      <MemoryRouter>
        <Propagator
          entries={germinatingCrops([holdPeriod])}
          awaitingApproval={[approvalBlocked]}
          basePath="/plot"
        />
      </MemoryRouter>
    );

    const bp = screen.getByRole('link', { name: /BP\.L/ });
    expect(within(bp).getByText('Needs approval')).toBeTruthy();
    expect(within(bp).queryByText('Not yet liftable')).toBeNull();
    expect(screen.getByText('Needs approval (1)')).toBeTruthy();
    expect(
      screen
        .getByRole('link', { name: 'Open Trading Rules' })
        .getAttribute('href')
    ).toBe('/settings');

    const zprx = screen.getByRole('link', { name: /ZPRX\.DE/ });
    expect(within(zprx).getByText('Ready 2026-11-06')).toBeTruthy();
  });

  it('still shows approval-blocked crops when nothing is serving a hold period', () => {
    render(
      <MemoryRouter>
        <Propagator
          entries={[]}
          awaitingApproval={[approvalBlocked]}
          basePath="/plot"
        />
      </MemoryRouter>
    );
    expect(screen.getByText(/Nothing in the propagator/)).toBeTruthy();
    expect(screen.getByText('Needs approval')).toBeTruthy();
  });
});
