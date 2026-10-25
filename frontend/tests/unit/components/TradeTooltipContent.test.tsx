import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import type { ComponentProps } from 'react';
import i18n from '@/i18n';
import { TradeTooltipContent } from '@/components/InstrumentDetail';
import { buildTradeMarkers } from '@/components/instrumentTradeMarkers';
import type { Transaction } from '@/types';

const CHART_DATES = ['2024-01-01', '2024-01-02', '2024-01-03'];

const TRADES = [
  {
    owner: 'alice',
    account: 'isa',
    id: 'buy-1',
    date: '2024-01-02',
    ticker: 'ABC.L',
    type: 'BUY',
    units: 10,
    price_gbp: 101.5,
  },
  {
    owner: 'bob',
    account: 'sipp',
    id: 'sell-1',
    date: '2024-01-03',
    ticker: 'ABC.L',
    type: 'SELL',
    units: 4,
    price_gbp: 103,
  },
] as Transaction[];

type Props = ComponentProps<typeof TradeTooltipContent>;

// Each trade line is built from several JSX text nodes, so match on the whole
// line's text rather than a single node.
const tradeLine = (text: string) => (_: string, el: Element | null) =>
  el?.tagName === 'DIV' &&
  el.children.length === 0 &&
  (el.textContent ?? '').replace(/\s+/g, ' ').trim() === text;

const renderTooltip = (label: string) =>
  render(
    <TradeTooltipContent
      {...({ active: true, label, payload: [] } as unknown as Props)}
      markers={buildTradeMarkers(TRADES, 'ABC.L', CHART_DATES)}
    />
  );

describe('TradeTooltipContent', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
  });

  it('lists side, trade date, units, price and owner/account for the hovered date', () => {
    renderTooltip('2024-01-02');

    expect(
      screen.getByText(
        tradeLine('Buy · 2024-01-02 · 10.00 units @ 101.50 · alice / isa')
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/bob \/ sipp/)).not.toBeInTheDocument();
  });

  it('shows the sell on its own date', () => {
    renderTooltip('2024-01-03');

    expect(
      screen.getByText(
        tradeLine('Sell · 2024-01-03 · 4.00 units @ 103.00 · bob / sipp')
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/alice \/ isa/)).not.toBeInTheDocument();
  });

  it('adds no trade details when the hovered date has no trade', () => {
    renderTooltip('2024-01-01');

    expect(
      screen.queryByText(/alice \/ isa|bob \/ sipp/)
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/units/)).not.toBeInTheDocument();
  });
});
