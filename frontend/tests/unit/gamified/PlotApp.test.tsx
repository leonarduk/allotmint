import {
  render,
  screen,
  waitFor,
  fireEvent,
  within,
} from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Portfolio } from '@/types';

const portfolio: Portfolio = {
  owner: 'steve',
  as_of: '2026-08-24',
  trades_this_month: 2,
  trades_remaining: 8,
  total_value_estimate_gbp: 10_000,
  accounts: [
    {
      account_type: 'stocks-isa',
      currency: 'GBP',
      owner: 'steve',
      value_estimate_gbp: 10_000,
      holdings: [
        {
          ticker: 'VUSA.L',
          name: 'Vanguard S&P 500',
          units: 40,
          market_value_gbp: 7_000,
          effective_cost_basis_gbp: 4_000,
          gain_gbp: 3_000,
          gain_pct: 75,
          day_change_gbp: 70,
          sector: 'Financials',
          region: 'US',
          instrument_type: 'ETF',
          days_held: 500,
          sell_eligible: true,
          last_price_date: '2026-08-24',
        },
        {
          ticker: 'WILT.L',
          name: 'Wilting Ltd',
          units: 5,
          market_value_gbp: 3_000,
          effective_cost_basis_gbp: 5_000,
          gain_gbp: -2_000,
          gain_pct: -40,
          day_change_gbp: -30,
          sector: 'Energy',
          region: 'UK',
          instrument_type: 'Equity',
          days_held: 4,
          sell_eligible: false,
        },
      ],
    },
  ],
};

const trailPayload = {
  tasks: [
    {
      id: 'water-beds',
      title: 'Review this week’s movers',
      type: 'daily',
      commentary: 'Two holdings moved more than 5%.',
      completed: false,
    },
    {
      id: 'set-alerts',
      title: 'Set an alert threshold',
      type: 'once',
      commentary: '',
      completed: true,
    },
  ],
  xp: 150,
  streak: 3,
  daily_totals: {},
  today: '2026-08-24',
};

const { mocks } = vi.hoisted(() => ({
  mocks: {
    getOwners: vi.fn(),
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

function renderPlot(path = '/plot') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/plot/*" element={<PlotApp />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getOwners.mockResolvedValue([
    { owner: 'steve', accounts: ['stocks-isa'] },
  ]);
  mocks.getPortfolio.mockResolvedValue(portfolio);
  mocks.getAllowances.mockResolvedValue({
    owner: 'steve',
    tax_year: '2026/27',
    allowances: { isa: { used: 5_000, limit: 20_000, remaining: 15_000 } },
  });
  mocks.getTrailTasks.mockResolvedValue(trailPayload);
  mocks.getQuotes.mockResolvedValue([]);
});

describe('Plot mode hub', () => {
  it('renders the HUD from real portfolio and XP figures', async () => {
    renderPlot();

    // 150 XP sits exactly on level 3 of the 25 * L * (L - 1) curve, so the
    // label is also proof the Trail XP reached the HUD.
    expect(await screen.findByText('Level 3 · 0/150 XP')).toBeInTheDocument();
    // Scoped to the heading: "The Plot" is also the first rail link's label.
    expect(
      screen.getByRole('heading', { name: /The Plot/ })
    ).toBeInTheDocument();
    // Scoped to the HUD: the same figures also appear on the bed cards below.
    const hud = screen.getByRole('banner');
    expect(within(hud).getByText('£10.0k')).toBeInTheDocument();
    expect(within(hud).getByText('£1.0k')).toBeInTheDocument();
    expect(within(hud).getByText('Seedling Sower')).toBeInTheDocument();
    // Trail streak of 3 renders its own HUD chip (matched by title, since the
    // bare "3" also appears in the level badge).
    expect(
      within(hud).getByTitle('Consecutive days of chores done')
    ).toHaveTextContent('3');
  });

  it('puts the best and worst performing crops on the stage', async () => {
    renderPlot();

    const stage = await screen.findByRole('region', { name: 'Featured crops' });
    expect(stage).toHaveTextContent('VUSA.L');
    expect(stage).toHaveTextContent('Star grower');
    expect(stage).toHaveTextContent('WILT.L');
    expect(stage).toHaveTextContent('Needs attention');
  });

  it('shows resource meters backed by trades, allowances and price freshness', async () => {
    renderPlot();

    expect(
      await screen.findByText('8 of 10 trades left this month')
    ).toBeInTheDocument();
    expect(
      screen.getByText('£15.0k of tax allowance headroom left')
    ).toBeInTheDocument();
    expect(
      screen.getByText('2 of 2 crops priced from fresh data')
    ).toBeInTheDocument();
  });

  it('offers an escape hatch back to the classic UI for the same owner', async () => {
    renderPlot();

    const link = await screen.findByRole('link', { name: /classic view/i });
    expect(link).toHaveAttribute('href', '/?owner=steve');
  });

  it('surfaces a retry when the portfolio cannot be loaded', async () => {
    mocks.getPortfolio.mockRejectedValue(new Error('backend down'));
    renderPlot();

    expect(await screen.findByRole('alert')).toHaveTextContent('backend down');
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledTimes(2));
  });
});

describe('Plot mode crop roster', () => {
  it('lists every crop and filters by bed', async () => {
    renderPlot('/plot/crops');

    expect(await screen.findByText('Crop roster (2/2)')).toBeInTheDocument();
    expect(screen.getByText('VUSA.L')).toBeInTheDocument();
    expect(screen.getByText('WILT.L')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /all beds/i }));
    expect(screen.getByRole('button', { name: /all beds/i })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  it('re-sorts the roster when a sort chip is pressed', async () => {
    renderPlot('/plot/crops');

    const gainChip = await screen.findByRole('button', { name: 'Growth' });
    fireEvent.click(gainChip);
    expect(gainChip).toHaveAttribute('aria-pressed', 'true');

    const tickers = screen
      .getAllByText(/^(VUSA\.L|WILT\.L)$/)
      .map((node) => node.textContent);
    expect(tickers[0]).toBe('VUSA.L');
  });
});

describe('Plot mode crop detail', () => {
  it('shows the holding ledger and its garden traits', async () => {
    renderPlot('/plot/crops/VUSA.L');

    expect(
      await screen.findByRole('heading', { name: /VUSA\.L — Vanguard S&P 500/ })
    ).toBeInTheDocument();
    expect(screen.getByText('Financials')).toBeInTheDocument();
    expect(screen.getByText('Cost basis')).toBeInTheDocument();
    expect(screen.getByText('£4.0k')).toBeInTheDocument();
    expect(
      screen.getByText(/Held 500 days · ready to lift/)
    ).toBeInTheDocument();
    // Root depth reuses the 7-star plot-share rating, so it must not be
    // labelled against the 5-point scale the other traits use.
    expect(screen.getByText('Lv 7/7')).toBeInTheDocument();
    expect(screen.getByText('Lv 4/5')).toBeInTheDocument();
  });

  it('explains itself when the ticker is not in the plot', async () => {
    renderPlot('/plot/crops/NOPE.L');

    expect(
      await screen.findByRole('heading', { name: 'Crop not found' })
    ).toBeInTheDocument();
  });
});

describe('Plot mode chores', () => {
  it('lists Trail tasks and completes one through the Trail endpoint', async () => {
    mocks.completeTrailTask.mockResolvedValue({
      ...trailPayload,
      tasks: trailPayload.tasks.map((task) => ({ ...task, completed: true })),
      xp: 160,
    });

    renderPlot('/plot/chores');

    const doIt = await screen.findByRole('button', { name: 'Do it' });
    expect(
      screen.getByText('Two holdings moved more than 5%.')
    ).toBeInTheDocument();

    fireEvent.click(doIt);
    await waitFor(() =>
      expect(mocks.completeTrailTask).toHaveBeenCalledWith('water-beds')
    );
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Do it' })).toBeNull()
    );
  });

  it('falls back to the Quests endpoint when Trail is unavailable', async () => {
    mocks.getTrailTasks.mockRejectedValue(new Error('404'));
    mocks.getQuests.mockResolvedValue({
      quests: [{ id: 'check_in', title: 'Check in', xp: 10, completed: false }],
      xp: 40,
      streak: 1,
    });

    renderPlot('/plot/chores');

    expect(await screen.findByText('Check in')).toBeInTheDocument();
    expect(screen.getByText('10 XP')).toBeInTheDocument();
  });

  it('says so when neither progress endpoint is available', async () => {
    mocks.getTrailTasks.mockRejectedValue(new Error('404'));
    mocks.getQuests.mockRejectedValue(new Error('404'));

    renderPlot('/plot/chores');

    expect(
      await screen.findByText(/Neither the Trail nor the Quests endpoint/)
    ).toBeInTheDocument();
  });
});
