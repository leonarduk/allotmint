import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'jest-axe';
import type { Portfolio } from '@/types';

const portfolio: Portfolio = {
  owner: 'steve',
  as_of: '2026-08-24',
  trades_this_month: 1,
  trades_remaining: 9,
  total_value_estimate_gbp: 5_000,
  accounts: [
    {
      account_type: 'stocks-isa',
      currency: 'GBP',
      owner: 'steve',
      value_estimate_gbp: 5_000,
      holdings: [
        {
          ticker: 'VUSA.L',
          name: 'Vanguard S&P 500',
          units: 10,
          market_value_gbp: 5_000,
          effective_cost_basis_gbp: 4_000,
          gain_gbp: 1_000,
          gain_pct: 25,
          day_change_gbp: 25,
          sector: 'Financials',
        },
      ],
    },
  ],
};

const { mocks } = vi.hoisted(() => ({
  mocks: {
    getOwners: vi.fn(),
    getGroups: vi.fn(),
    getPortfolio: vi.fn(),
    getAllowances: vi.fn(),
    getTrailTasks: vi.fn(),
    getQuests: vi.fn(),
    completeTrailTask: vi.fn(),
    completeQuest: vi.fn(),
    getQuotes: vi.fn(),
  },
}));

vi.mock('@/api', () => mocks);

const { default: PlotApp } = await import('@/gamified/PlotApp');

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getOwners.mockResolvedValue([
    { owner: 'steve', accounts: ['stocks-isa'] },
  ]);
  mocks.getGroups.mockResolvedValue([]);
  mocks.getPortfolio.mockResolvedValue(portfolio);
  mocks.getAllowances.mockResolvedValue({
    owner: 'steve',
    tax_year: '2026/27',
    allowances: {},
  });
  mocks.getTrailTasks.mockResolvedValue({
    tasks: [
      {
        id: 'a',
        title: 'Check the movers',
        type: 'daily',
        commentary: '',
        completed: false,
      },
    ],
    xp: 60,
    streak: 1,
    daily_totals: {},
    today: '2026-08-24',
  });
});

/**
 * Arcade chrome is the easiest place to accidentally ship unlabelled
 * controls and bare-colour meaning, so both screens get an axe pass.
 */
describe('Plot mode accessibility', () => {
  it('has no detectable violations on the hub', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/plot']}>
        <Routes>
          <Route path="/plot/*" element={<PlotApp />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByRole('region', { name: 'Featured crops' });
    expect(await axe(container)).toHaveNoViolations();
  });

  it('has no detectable violations on the chores screen', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/plot/chores']}>
        <Routes>
          <Route path="/plot/*" element={<PlotApp />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByText('Check the movers');
    expect(await axe(container)).toHaveNoViolations();
  });

  it('has no detectable violations on the season ladder', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/plot/season']}>
        <Routes>
          <Route path="/plot/*" element={<PlotApp />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByRole('heading', { name: /Growing season/ });
    expect(await axe(container)).toHaveNoViolations();
  });

  it('has no detectable violations on the crop roster', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/plot/crops']}>
        <Routes>
          <Route path="/plot/*" element={<PlotApp />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByRole('searchbox', { name: 'Search crops' });
    expect(await axe(container)).toHaveNoViolations();
  });
});
