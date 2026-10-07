import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { InstrumentTechnicalsPanel } from '@/components/InstrumentTechnicalsPanel';
import * as api from '@/api';
import type { InstrumentTechnicals } from '@/types';

vi.mock('@/api', () => ({ getInstrumentTechnicals: vi.fn() }));
const mockGetTechnicals = vi.mocked(api.getInstrumentTechnicals);

const technicals = (
  overrides: Partial<InstrumentTechnicals> = {}
): InstrumentTechnicals => ({
  ticker: 'ADBE.N',
  name: 'Adobe',
  price: 237.69,
  price_currency: 'USD',
  as_of: '2026-10-02',
  moving_averages: {
    sma_20: 247.05,
    sma_50: 258.49,
    sma_200: 259.87,
    vs_sma_20: -0.0379,
    vs_sma_50: -0.0805,
    vs_sma_200: -0.0854,
    trend: 'downtrend',
    cross_state: 'death',
    last_cross: null,
    last_cross_date: null,
  },
  rsi: { value: 41.02, period: 14, zone: 'neutral' },
  macd: {
    macd: -7.08,
    signal: -6.05,
    histogram: -1.03,
    last_crossover: 'bearish',
    last_crossover_date: '2026-09-03',
  },
  bollinger: {
    upper: 267.18,
    middle: 247.05,
    lower: 226.93,
    percent_b: 0.2673,
    bandwidth: 0.1629,
  },
  range_52w: {
    high: 359.91,
    high_date: '2025-10-28',
    low: 193.41,
    low_date: '2026-06-25',
    position: 0.2659,
    from_high: -0.3396,
  },
  returns: { '1m': -0.1505, '3m': 0.0818, '6m': -0.0215, '1y': -0.3237 },
  relative_strength: {
    benchmark: {
      ticker: 'VUSA.L',
      name: 'S&P 500 (Vanguard VUSA ETF)',
      source: 'exchange_default',
    },
    excess_3m: 0.0436,
    excess_1y: -0.4914,
  },
  signals: ['MACD last crossed below its signal line on 2026-09-03 (bearish).'],
  data_quality: {
    price_last_date: '2026-10-02',
    price_stale: false,
    data_points: 502,
    warnings: [],
  },
  ...overrides,
});

describe('InstrumentTechnicalsPanel', () => {
  beforeEach(() => {
    mockGetTechnicals.mockReset();
  });

  it('shows trend, momentum, range and returns', async () => {
    mockGetTechnicals.mockResolvedValue(technicals());

    render(<InstrumentTechnicalsPanel ticker="ADBE.N" />);

    const trend = await screen.findByRole('table', { name: 'Trend' });
    expect(within(trend).getByText('Downtrend')).toBeInTheDocument();
    expect(within(trend).getByText('247.05 USD')).toBeInTheDocument();
    const momentum = screen.getByRole('table', { name: 'Momentum' });
    expect(within(momentum).getByText('41')).toBeInTheDocument();
    expect(
      within(momentum).getByText('Bearish (2026-09-03)')
    ).toBeInTheDocument();
    const returns = screen.getByRole('table', { name: 'Returns' });
    expect(within(returns).getByText('vs VUSA.L (12m)')).toBeInTheDocument();
    expect(
      screen.getByText(/crossed below its signal line/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/not buy or sell recommendations/)
    ).toBeInTheDocument();
    expect(mockGetTechnicals).toHaveBeenCalledWith(
      'ADBE.N',
      expect.any(AbortSignal)
    );
  });

  it('omits relative strength when there is no comparable benchmark', async () => {
    mockGetTechnicals.mockResolvedValue(
      technicals({
        relative_strength: {
          benchmark: {
            ticker: null,
            name: null,
            source: 'none',
            asset_class: 'bond',
          },
          excess_3m: null,
          excess_1y: null,
        },
      })
    );

    render(<InstrumentTechnicalsPanel ticker="GILG.L" />);

    const returns = await screen.findByRole('table', { name: 'Returns' });
    expect(within(returns).getByText('12 months')).toBeInTheDocument();
    expect(within(returns).queryByText(/^vs /)).not.toBeInTheDocument();
    expect(returns.textContent).not.toMatch(/null|undefined/);
  });

  it('explains the jargon with info tips linking to the glossary', async () => {
    mockGetTechnicals.mockResolvedValue(technicals());

    render(<InstrumentTechnicalsPanel ticker="ADBE.N" />);

    const trend = await screen.findByRole('table', { name: 'Trend' });
    expect(
      within(trend).getByText('Death cross (50 below 200)')
    ).toBeInTheDocument();
    const crossTip = within(trend).getByRole('button', {
      name: 'What does Golden cross and death cross mean?',
    });
    fireEvent.click(crossTip);
    expect(crossTip).toHaveAttribute('aria-expanded', 'true');
    const popover = document.getElementById(
      crossTip.getAttribute('aria-controls')!
    )!;
    expect(popover.textContent).toMatch(/death cross is when it falls below/);
    expect(within(popover).getByRole('link')).toHaveAttribute(
      'href',
      '/metrics-explained#golden-death-cross'
    );
    expect(
      screen.getByRole('link', { name: 'What do these terms mean?' })
    ).toHaveAttribute('href', '/metrics-explained#technical-analysis');
    expect(
      screen.getByRole('button', { name: /What does RSI .* mean\?/ })
    ).toBeInTheDocument();
  });

  it('lists data-quality warnings above the numbers', async () => {
    mockGetTechnicals.mockResolvedValue(
      technicals({
        data_quality: {
          price_last_date: '2026-09-01',
          price_stale: true,
          data_points: 60,
          warnings: [
            'Only 60 closes available; indicators needing more history are left empty.',
          ],
        },
      })
    );

    render(<InstrumentTechnicalsPanel ticker="ADBE.N" />);

    const alert = await screen.findByRole('alert', { name: 'Data quality' });
    expect(within(alert).getByText(/Only 60 closes/)).toBeInTheDocument();
  });

  it('explains when the deployment has no technicals', async () => {
    mockGetTechnicals.mockImplementation(() =>
      Promise.reject(Object.assign(new Error('gated'), { status: 402 }))
    );

    render(<InstrumentTechnicalsPanel ticker="ADBE.N" />);

    const message = await screen.findByText(/not available in this deployment/);
    expect(message).toBeInTheDocument();
  });
});
