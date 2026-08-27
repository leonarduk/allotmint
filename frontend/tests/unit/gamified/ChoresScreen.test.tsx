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

function renderChores() {
  return render(
    <MemoryRouter initialEntries={['/plot/chores']}>
      <Routes>
        <Route path="/plot/*" element={<PlotApp />} />
      </Routes>
    </MemoryRouter>
  );
}

/**
 * `water_the_beds` deliberately has no entry in ChoresScreen's `CHORE_LINKS`
 * map, so clicking it calls `completeChore` directly (#7058 moved most
 * chores to a "Go" deep-link instead; only unmapped ids still complete
 * in-place, which is what #7188's pending/error states are about).
 */
const UNMAPPED_TASK = {
  id: 'water_the_beds',
  title: 'Water the beds',
  type: 'daily' as const,
  commentary: '',
  completed: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  mocks.getOwners.mockResolvedValue([
    { owner: 'steve', accounts: ['stocks-isa'] },
  ]);
  mocks.getPortfolio.mockResolvedValue(portfolio);
  mocks.getAllowances.mockResolvedValue({
    owner: 'steve',
    tax_year: '2026-2027',
    allowances: {},
  });
  mocks.getQuests.mockResolvedValue({ quests: [] });
  mocks.getTrailTasks.mockResolvedValue({
    tasks: [UNMAPPED_TASK],
    xp: 100,
    streak: 0,
    daily_totals: {},
    today: '2026-08-24',
  });
});

describe('ChoresScreen completion (#7188)', () => {
  it('shows a pending state on the button while the completion POST is in flight', async () => {
    let resolveCompletion: (value: unknown) => void = () => {};
    mocks.completeTrailTask.mockReturnValue(
      new Promise((resolve) => {
        resolveCompletion = resolve;
      })
    );

    renderChores();

    const button = await screen.findByRole('button', { name: 'Do it' });
    fireEvent.click(button);

    // While the request is in flight the button must read as busy, not dead.
    const pendingButton = await screen.findByRole('button', {
      name: 'Completing…',
    });
    expect(pendingButton).toBeDisabled();
    expect(pendingButton).toHaveAttribute('aria-busy', 'true');

    resolveCompletion({
      tasks: [{ ...UNMAPPED_TASK, completed: true }],
      xp: 110,
      streak: 0,
      daily_totals: {},
      today: '2026-08-24',
    });

    expect(await screen.findByRole('button', { name: 'Done' })).toBeDisabled();
  });

  it('surfaces a rejected completion as an inline error with a retry, not silence', async () => {
    mocks.completeTrailTask.mockRejectedValueOnce(new Error('network down'));

    renderChores();

    const button = await screen.findByRole('button', { name: 'Do it' });
    fireEvent.click(button);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/could not complete/i);

    // The row stays actionable: no false "done" state, and the button is
    // enabled again so the user can retry rather than seeing a dead control.
    const retryButton = await screen.findByRole('button', {
      name: 'Try again',
    });
    expect(retryButton).not.toBeDisabled();

    mocks.completeTrailTask.mockResolvedValueOnce({
      tasks: [{ ...UNMAPPED_TASK, completed: true }],
      xp: 110,
      streak: 0,
      daily_totals: {},
      today: '2026-08-24',
    });
    fireEvent.click(retryButton);

    await waitFor(() => expect(mocks.completeTrailTask).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole('button', { name: 'Done' })).toBeDisabled();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
