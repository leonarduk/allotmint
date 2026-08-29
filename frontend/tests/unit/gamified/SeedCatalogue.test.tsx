import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Portfolio } from '@/types';

const portfolio: Portfolio = {
  owner: 'steve',
  as_of: '2026-08-24',
  trades_this_month: 2,
  trades_remaining: 8,
  total_value_estimate_gbp: 10_000,
  accounts: [],
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

// Imported after the mock so the module graph picks up the stubbed api.
const { default: PlotApp } = await import('@/gamified/PlotApp');

function renderSeeds() {
  return render(
    <MemoryRouter initialEntries={['/plot/seeds']}>
      <Routes>
        <Route path="/plot/*" element={<PlotApp />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  mocks.getOwners.mockResolvedValue([
    { owner: 'steve', accounts: ['stocks-isa'] },
  ]);
  mocks.getGroups.mockResolvedValue([]);
  mocks.getPortfolio.mockResolvedValue(portfolio);
  mocks.getAllowances.mockResolvedValue({
    owner: 'steve',
    tax_year: '2026-2027',
    allowances: {},
  });
  mocks.getTrailTasks.mockResolvedValue({
    tasks: [],
    xp: 0,
    streak: 0,
    daily_totals: {},
    today: '2026-08-24',
  });
});

describe('Seed catalogue', () => {
  it('actually issues a request and renders real watchlist quotes', async () => {
    mocks.getQuotes.mockResolvedValue([
      {
        symbol: 'VUSA.L',
        name: 'Vanguard S&P 500',
        last: 92.5,
        open: 92,
        high: 93,
        low: 91,
        change: 0.5,
        changePct: 0.54,
        volume: 1000,
        marketTime: null,
        marketState: 'REGULAR',
      },
    ]);
    window.localStorage.setItem('watchlistSymbols', 'VUSA.L');

    renderSeeds();

    // The loading state must actually resolve, not hang forever.
    expect(
      await screen.findByText('Available seed (1)')
    ).toBeInTheDocument();
    expect(screen.queryByText(/Checking the seed trays/)).toBeNull();
    expect(screen.getByText('VUSA.L')).toBeInTheDocument();
    expect(mocks.getQuotes).toHaveBeenCalledWith(
      ['VUSA.L'],
      expect.anything()
    );
  });

  it('shows a distinct empty-state when the watchlist has no symbols', async () => {
    mocks.getQuotes.mockResolvedValue([]);
    window.localStorage.setItem('watchlistSymbols', ',,,');

    renderSeeds();

    expect(
      await screen.findByText(/Your watchlist is empty/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/Checking the seed trays/)).toBeNull();
    expect(mocks.getQuotes).not.toHaveBeenCalled();
  });

  it('shows a visible error with retry when the quote fetch fails', async () => {
    mocks.getQuotes.mockRejectedValueOnce(new Error('quotes down'));
    window.localStorage.setItem('watchlistSymbols', 'VUSA.L');

    renderSeeds();

    expect(await screen.findByRole('alert')).toHaveTextContent('quotes down');
    // The error state must not be muddled with the generic empty-state copy.
    expect(screen.queryByText(/Your watchlist is empty/)).toBeNull();
    expect(screen.queryByText(/Checking the seed trays/)).toBeNull();

    mocks.getQuotes.mockResolvedValueOnce([
      {
        symbol: 'VUSA.L',
        name: 'Vanguard S&P 500',
        last: 92.5,
        open: 92,
        high: 93,
        low: 91,
        change: 0.5,
        changePct: 0.54,
        volume: 1000,
        marketTime: null,
        marketState: 'REGULAR',
      },
    ]);
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));

    await waitFor(() => expect(mocks.getQuotes).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByText('Available seed (1)')
    ).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
