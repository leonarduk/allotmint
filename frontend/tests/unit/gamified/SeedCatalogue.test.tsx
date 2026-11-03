import {
  act,
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Portfolio, QuoteRow } from '@/types';

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
const { createWatchlist, setActiveWatchlist, readWatchlists } = await import(
  '@/lib/watchlistStore'
);

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
  // PlotDataContext fetches groups alongside owners (#7189) to filter the
  // grower picker; an empty list here just means "no group filtering",
  // which keeps this file's single-owner scenarios unaffected.
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

function quote(
  symbol: string,
  overrides: Partial<QuoteRow> = {}
): QuoteRow {
  return {
    symbol,
    name: `${symbol} name`,
    last: 10,
    open: 10,
    high: 10,
    low: 10,
    change: 0,
    changePct: 0,
    volume: 0,
    marketTime: null,
    marketState: 'REGULAR',
    ...overrides,
  };
}

describe('Seed shed: seeds vs weather (#7203)', () => {
  it('shows indices, FX and futures as weather, not unsown seed packets', async () => {
    mocks.getQuotes.mockResolvedValue([
      quote('VUSA.L', { currency: 'GBX', quoteType: 'ETF', last: 92.5 }),
      quote('^VIX', { quoteType: 'INDEX', last: 15.21 }),
      quote('USDGBP=X', { currency: 'GBP', quoteType: 'CURRENCY', last: 0.74 }),
      quote('GC=F', { currency: 'USD', quoteType: 'FUTURE', last: 4647.4 }),
    ]);
    window.localStorage.setItem('watchlistSymbols', 'VUSA.L,^VIX,USDGBP=X,GC=F');

    renderSeeds();

    expect(await screen.findByText('Available seed (1)')).toBeInTheDocument();
    const weather = screen.getByRole('region', { name: 'The weather (3)' });
    for (const symbol of ['^VIX', 'USDGBP=X', 'GC=F']) {
      expect(within(weather).getByText(symbol)).toBeInTheDocument();
    }
    // No buy-adjacent framing anywhere on the screen.
    expect(screen.queryByText(/not sown yet/i)).toBeNull();
    expect(within(weather).queryByRole('link')).toBeNull();
    expect(within(weather).queryByText('Not in your plot')).toBeNull();
    expect(screen.getByText('Not in your plot')).toBeInTheDocument();
  });

  it('labels every price with its currency or unit', async () => {
    mocks.getQuotes.mockResolvedValue([
      quote('VUSA.L', { currency: 'GBX', quoteType: 'ETF', last: 92.5 }),
      quote('^FTSE', { currency: 'GBP', quoteType: 'INDEX', last: 10878.12 }),
      quote('BTC-USD', { last: 78377.15 }),
      quote('ZZZ', { last: 3 }),
    ]);
    window.localStorage.setItem('watchlistSymbols', 'VUSA.L,^FTSE,BTC-USD,ZZZ');

    renderSeeds();

    expect(await screen.findByText('92.50 GBX')).toBeInTheDocument();
    // An index level is points, even when the feed also sends a currency.
    expect(screen.getByText('10878 pts')).toBeInTheDocument();
    expect(screen.getByText('78377 USD')).toBeInTheDocument();
    // Unknown is said out loud, never guessed.
    expect(screen.getByText('3.00 (unit unknown)')).toBeInTheDocument();
  });

  it('keeps the way to manage the watchlist visible when rows are present', async () => {
    mocks.getQuotes.mockResolvedValue([quote('VUSA.L', { quoteType: 'ETF' })]);
    window.localStorage.setItem('watchlistSymbols', 'VUSA.L');

    renderSeeds();

    expect(await screen.findByText('VUSA.L')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'classic watchlist' })
    ).toHaveAttribute('href', '/watchlist');
  });

  it('does not claim zero seeds while quotes are loading', async () => {
    let resolve: (rows: QuoteRow[]) => void = () => {};
    mocks.getQuotes.mockReturnValue(
      new Promise<QuoteRow[]>((done) => {
        resolve = done;
      })
    );
    window.localStorage.setItem('watchlistSymbols', 'VUSA.L');

    renderSeeds();

    expect(await screen.findByText(/Checking the seed trays/)).toBeInTheDocument();
    expect(screen.getByText('Available seed')).toBeInTheDocument();
    expect(screen.queryByText('Available seed (0)')).toBeNull();

    await act(async () => {
      resolve([quote('VUSA.L', { quoteType: 'ETF' })]);
    });
    expect(await screen.findByText('Available seed (1)')).toBeInTheDocument();
  });
});

describe('Seed catalogue', () => {
  it('re-quotes when the active watchlist changes, without a remount', async () => {
    mocks.getQuotes.mockImplementation(async (symbols: string[]) =>
      symbols.map((symbol) => ({
        symbol,
        name: `${symbol} name`,
        last: 1,
        open: 1,
        high: 1,
        low: 1,
        change: 0,
        changePct: 0,
        volume: 0,
        marketTime: null,
        marketState: 'REGULAR',
      }))
    );
    window.localStorage.setItem('watchlistSymbols', 'VUSA.L');
    renderSeeds();
    expect(await screen.findByText('VUSA.L')).toBeInTheDocument();

    const firstId = readWatchlists().activeId;
    // Creating a list also makes it active.
    act(() => {
      createWatchlist('Miners', ['RIO.L']);
    });
    expect(await screen.findByText('RIO.L')).toBeInTheDocument();
    expect(screen.queryByText('VUSA.L')).toBeNull();
    expect(mocks.getQuotes).toHaveBeenLastCalledWith(
      ['RIO.L'],
      expect.anything()
    );

    act(() => {
      setActiveWatchlist(firstId);
    });
    expect(await screen.findByText('VUSA.L')).toBeInTheDocument();
    expect(screen.queryByText('RIO.L')).toBeNull();
  });

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
