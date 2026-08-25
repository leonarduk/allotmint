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
          days_until_eligible: 26,
          next_eligible_sell_date: '2026-09-19',
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
  daily_totals: {
    '2026-08-22': { completed: 2, total: 2 },
    '2026-08-23': { completed: 2, total: 2 },
    '2026-08-24': { completed: 1, total: 2 },
  },
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
  window.localStorage.clear();
  window.sessionStorage.clear();
  mocks.getOwners.mockResolvedValue([
    { owner: 'steve', accounts: ['stocks-isa'] },
  ]);
  mocks.getPortfolio.mockResolvedValue(portfolio);
  mocks.getAllowances.mockResolvedValue({
    owner: 'steve',
    // The backend's own "YYYY-YYYY" form (see current_tax_year).
    tax_year: '2026-2027',
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

  it('shows a distinct unavailable notice on the FEED meter when the allowances fetch fails, not the empty-data copy', async () => {
    mocks.getAllowances.mockRejectedValue(
      Object.assign(new Error('HTTP 402 - Payment Required'), { status: 402 })
    );
    renderPlot();

    expect(
      await screen.findByText('Allowances unavailable right now')
    ).toBeInTheDocument();
    expect(
      screen.queryByText('No allowance data for this grower yet')
    ).toBeNull();
    expect(
      screen.queryByText(/of tax allowance headroom left/)
    ).toBeNull();
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

    expect(
      await screen.findByRole('heading', { name: /Crop roster \(2\/2\)/ })
    ).toBeInTheDocument();
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

  it('shows the not-found panel for a malformed crop id rather than throwing', async () => {
    // React Router passes a bad percent-sequence through undecoded, so an
    // unguarded decodeURIComponent threw URIError mid-render and the screen
    // fell into the error boundary instead of answering the question.
    renderPlot('/plot/crops/%zz');

    expect(
      await screen.findByRole('heading', { name: 'Crop not found' })
    ).toBeInTheDocument();
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

  it('completes only the clicked chore when several daily chores are mid-list (#7002)', async () => {
    // Regression test for #7002: the "Do it" button must resolve the chore
    // to complete by its stable id, not by array position, even when other
    // chores in the list are already done either side of it.
    const midListPayload = {
      ...trailPayload,
      tasks: [
        {
          id: 'log_in',
          title: 'Log in',
          type: 'daily',
          commentary: '',
          completed: true,
        },
        {
          id: 'check_overview',
          title: 'Check overview',
          type: 'daily',
          commentary: '',
          completed: false,
        },
        {
          id: 'research_new_stock',
          title: 'Research a new stock',
          type: 'daily',
          commentary: '',
          completed: false,
        },
        {
          id: 'run_a_report',
          title: 'Run a report',
          type: 'daily',
          commentary: '',
          completed: true,
        },
      ],
      xp: 20,
    };
    mocks.getTrailTasks.mockResolvedValue(midListPayload);
    mocks.completeTrailTask.mockResolvedValue({
      ...midListPayload,
      tasks: midListPayload.tasks.map((task) =>
        task.id === 'research_new_stock' ? { ...task, completed: true } : task
      ),
      xp: 30,
    });

    renderPlot('/plot/chores');

    const researchRow = (
      await screen.findByText('Research a new stock')
    ).closest('li')!;
    const checkOverviewRow = screen
      .getByText('Check overview')
      .closest('li')!;

    fireEvent.click(within(researchRow).getByRole('button', { name: 'Do it' }));

    // The clicked chore's own id is sent to the backend, not a neighbour's.
    await waitFor(() =>
      expect(mocks.completeTrailTask).toHaveBeenCalledWith('research_new_stock')
    );
    expect(mocks.completeTrailTask).not.toHaveBeenCalledWith('check_overview');

    // Only the clicked row flips to done; its untouched neighbour stays actionable.
    await waitFor(() =>
      expect(
        within(researchRow).getByRole('button', { name: 'Done' })
      ).toBeInTheDocument()
    );
    expect(
      within(checkOverviewRow).getByRole('button', { name: 'Do it' })
    ).toBeInTheDocument();
  });

  it('links "Check overview" to the classic overview instead of self-completing (#7003)', async () => {
    mocks.getTrailTasks.mockResolvedValue({
      ...trailPayload,
      tasks: [
        {
          id: 'check_overview',
          title: 'Check overview',
          type: 'daily',
          commentary: 'Review your portfolio overview for any changes.',
          completed: false,
        },
      ],
    });

    renderPlot('/plot/chores');

    const goButton = await screen.findByRole('button', { name: 'Go' });
    fireEvent.click(goButton);

    // Navigating there is not itself completion — only the classic overview
    // page marking the pending chore visited does that (App.tsx). Clicking
    // "Go" sets the marker it reads, keyed to this chore id.
    expect(sessionStorage.getItem('allotmint:pendingChore')).toBe(
      'check_overview'
    );
    expect(mocks.completeTrailTask).not.toHaveBeenCalled();
  });

  it('links "Adjust your alert threshold" and "Create your first savings goal" to their real pages without a pending-visit marker', async () => {
    mocks.getTrailTasks.mockResolvedValue({
      ...trailPayload,
      tasks: [
        {
          id: 'set_alert_threshold',
          title: 'Adjust your alert threshold',
          type: 'once',
          commentary: '',
          completed: false,
        },
        {
          id: 'create_goal',
          title: 'Create your first savings goal',
          type: 'once',
          commentary: '',
          completed: false,
        },
      ],
    });

    renderPlot('/plot/chores');

    const [thresholdGo] = await screen.findAllByRole('button', { name: 'Go' });
    fireEvent.click(thresholdGo);

    // These two are already completed server-side once real data exists (a
    // custom threshold / a saved goal), so there is nothing for a visit
    // marker to trigger and the click never self-completes.
    expect(sessionStorage.getItem('allotmint:pendingChore')).toBeNull();
    expect(mocks.completeTrailTask).not.toHaveBeenCalled();
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

describe('Plot mode streak path', () => {
  it("stamps the week from the Trail's real per-day totals", async () => {
    renderPlot();

    const history = await screen.findByRole('list', {
      name: 'Chore history for the last week',
    });
    // Two full days and one partial, from the fixture's daily_totals.
    expect(
      within(history).getByText('2026-08-23: 2 of 2 chores done')
    ).toBeInTheDocument();
    expect(
      within(history).getByText('2026-08-24: 1 of 2 chores done')
    ).toBeInTheDocument();
    // Days the backend has no record for stay blank rather than being guessed.
    expect(
      within(history).getByText('2026-08-18: no chores recorded')
    ).toBeInTheDocument();
  });
});

describe('Plot mode propagator', () => {
  it('shows holdings still inside their minimum holding period', async () => {
    renderPlot();

    expect(await screen.findByText('Propagator (1)')).toBeInTheDocument();
    expect(screen.getByText('4 / 30 days')).toBeInTheDocument();
    expect(screen.getByText('Ready 2026-09-19')).toBeInTheDocument();
  });

  it('spells out the holding period on the crop detail screen', async () => {
    renderPlot('/plot/crops/WILT.L');

    expect(
      await screen.findByText(/in the propagator until 2026-09-19/)
    ).toBeInTheDocument();
  });
});

describe('Plot mode season track', () => {
  it('counts down the real UK tax year from the allowances endpoint', async () => {
    renderPlot('/plot/season');

    expect(
      await screen.findByRole('heading', { name: /Growing season 2026\/27/ })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/^Ends in \d+ days? and \d+ hours?$/)
    ).toBeInTheDocument();
  });

  it('lists tiered goals driven by real portfolio figures', async () => {
    renderPlot('/plot/season');

    // £10,000 plot value clears the £1k and £10k tiers but not £50k.
    expect(
      await screen.findByRole('heading', { name: /Grow the plot \(2\/4\)/ })
    ).toBeInTheDocument();
    expect(screen.getByText('Grow the plot to £50.0k')).toBeInTheDocument();
    // £5,000 of allowance used clears the first tier only.
    expect(
      screen.getByRole('heading', { name: /Feed the beds \(2\/4\)/ })
    ).toBeInTheDocument();
  });

  it('says so when the backend reports no tax year', async () => {
    mocks.getAllowances.mockResolvedValue({
      owner: 'steve',
      tax_year: null,
      allowances: {},
    });
    renderPlot('/plot/season');

    expect(
      await screen.findByText(/No tax year reported for this grower/)
    ).toBeInTheDocument();
  });

  it('shows the same distinct unavailable notice, not "no tax year", when the allowances fetch fails', async () => {
    mocks.getAllowances.mockRejectedValue(
      Object.assign(new Error('HTTP 402 - Payment Required'), { status: 402 })
    );
    renderPlot('/plot/season');

    // Countdown copy, and the "Feed the beds" milestone tiers, all use the
    // same notice instead of "no tax year" / a £0.00 progress bar (goal
    // titles stay visible; only the meter/value area swaps to error copy).
    const notices = await screen.findAllByText('Allowances unavailable right now');
    expect(notices.length).toBeGreaterThan(1);
    expect(
      screen.queryByText(/No tax year reported for this grower/)
    ).toBeNull();
    expect(
      screen.getByText("Use £1.0k of this season's allowances")
    ).toBeInTheDocument();
  });
});

describe('Plot mode roster search and favourites', () => {
  it('filters the roster by a free-text search', async () => {
    renderPlot('/plot/crops');

    const search = await screen.findByRole('searchbox', {
      name: 'Search crops',
    });
    fireEvent.change(search, { target: { value: 'wilting' } });

    expect(
      screen.getByRole('heading', { name: /Crop roster \(1\/2\)/ })
    ).toBeInTheDocument();
    expect(screen.getByText('WILT.L')).toBeInTheDocument();
    expect(screen.queryByText('VUSA.L')).toBeNull();

    fireEvent.change(search, { target: { value: 'no such crop' } });
    expect(
      screen.getByText('No crops match those filters.')
    ).toBeInTheDocument();
  });

  it('marks a favourite, persists it, and filters on it', async () => {
    renderPlot('/plot/crops');

    const star = await screen.findByRole('button', {
      name: 'Add VUSA.L to favourites',
    });
    fireEvent.click(star);
    expect(
      screen.getByRole('button', { name: 'Remove VUSA.L from favourites' })
    ).toHaveAttribute('aria-pressed', 'true');

    // Marks are this browser's own, namespaced per grower.
    expect(
      JSON.parse(
        window.localStorage.getItem('allotmint:plot:favourites:steve') ?? '[]'
      )
    ).toEqual(['VUSA.L']);

    fireEvent.click(screen.getByRole('button', { name: /Favourites \(1\)/ }));
    expect(
      screen.getByRole('heading', { name: /Crop roster \(1\/2\)/ })
    ).toBeInTheDocument();
    expect(screen.queryByText('WILT.L')).toBeNull();
  });
});

describe('Plot mode provider hardening', () => {
  it("does not leave the previous grower's figures on screen when a switch fails", async () => {
    mocks.getOwners.mockResolvedValue([
      { owner: 'steve', accounts: ['stocks-isa'] },
      { owner: 'alex', accounts: ['stocks-isa'] },
    ]);
    renderPlot();

    const hud = screen.getByRole('banner');
    await waitFor(() =>
      expect(within(hud).getByText('£10.0k')).toBeInTheDocument()
    );

    mocks.getPortfolio.mockRejectedValue(new Error('alex is unavailable'));
    fireEvent.change(screen.getByLabelText('Grower'), {
      target: { value: 'alex' },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'alex is unavailable'
    );
    // Steve's plot value must not still be sitting under Alex's name.
    expect(within(hud).queryByText('£10.0k')).toBeNull();
  });

  it('stops loading with a distinct message when grower discovery fails', async () => {
    mocks.getOwners.mockRejectedValue(new Error('offline'));
    renderPlot();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the list of growers.'
    );
    // The spinner must not be left running with no way out.
    expect(screen.queryByText(/Walking down to the allotment/)).toBeNull();
    expect(
      screen.getByRole('button', { name: /try again/i })
    ).toBeInTheDocument();
  });

  it('says so when the account genuinely has no growers', async () => {
    mocks.getOwners.mockResolvedValue([]);
    renderPlot();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No growers found for this account.'
    );
  });

  it('keeps at most one chore completion in flight', async () => {
    // Each reply is a whole server snapshot, so two in flight resolve
    // last-write-wins and an out-of-order pair can un-tick a done chore.
    // Serialising is the mechanism that prevents that, so it is what is tested.
    const trailWith = (done: string[]) => ({
      ...trailPayload,
      tasks: trailPayload.tasks.map((task) => ({
        ...task,
        completed: done.includes(task.id),
      })),
    });

    let resolveFirst: (value: unknown) => void = () => {};
    mocks.completeTrailTask
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve;
          })
      )
      .mockImplementationOnce(async () =>
        trailWith(['water-beds', 'set-alerts'])
      );

    renderPlot('/plot/chores');

    const doIt = await screen.findByRole('button', { name: 'Do it' });
    fireEvent.click(doIt);
    fireEvent.click(doIt);

    await waitFor(() =>
      expect(mocks.completeTrailTask).toHaveBeenCalledTimes(1)
    );
    // The second click stays queued while the first is unresolved.
    expect(mocks.completeTrailTask).toHaveBeenCalledTimes(1);

    resolveFirst(trailWith(['water-beds']));
    await waitFor(() =>
      expect(mocks.completeTrailTask).toHaveBeenCalledTimes(2)
    );
  });
});
