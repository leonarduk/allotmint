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

/**
 * Renders the chores screen and returns its one "Do it" button, asserting
 * along the way that `water_the_beds` is still unmapped in `CHORE_LINKS`.
 * If someone later adds it there, the button would render "Go" and every
 * assertion below it would fail with a confusing timeout (waiting on a
 * "Completing…"/error state that never arrives because the click just
 * navigated instead) rather than this clear, specific mismatch.
 */
async function findDoItButton() {
  const button = await screen.findByRole('button');
  expect(button).toHaveAccessibleName('Do it');
  return button;
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
  it('shows a pending state on the button while the completion POST is in flight, without losing focus', async () => {
    let resolveCompletion: (value: unknown) => void = () => {};
    mocks.completeTrailTask.mockReturnValue(
      new Promise((resolve) => {
        resolveCompletion = resolve;
      })
    );

    renderChores();

    const button = await findDoItButton();
    button.focus();
    fireEvent.click(button);

    // While the request is in flight the button must read as busy, not
    // dead — and it must stay enabled and keep focus (finding 1: disabling
    // it here used to blur focus onto <body> on the exact click that
    // needed it most, right before a possible failure).
    const pendingButton = await screen.findByRole('button', {
      name: 'Completing…',
    });
    expect(pendingButton).toBe(button);
    expect(pendingButton).not.toBeDisabled();
    expect(pendingButton).toHaveAttribute('aria-busy', 'true');
    expect(document.activeElement).toBe(pendingButton);

    // A second activation while still pending must not fire a second
    // request (finding 1's re-entry guard, now that the button no longer
    // natively disables itself to block that).
    fireEvent.click(pendingButton);
    expect(mocks.completeTrailTask).toHaveBeenCalledTimes(1);

    // The pending state is also announced to a screen reader via an
    // always-mounted sr-only status region, not just visually (finding 2).
    expect(screen.getByRole('status')).toHaveTextContent(
      'Water the beds: completing…'
    );

    resolveCompletion({
      tasks: [{ ...UNMAPPED_TASK, completed: true }],
      xp: 110,
      streak: 0,
      daily_totals: {},
      today: '2026-08-24',
    });

    expect(await screen.findByRole('button', { name: 'Done' })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('');
  });

  it('surfaces a rejected completion as an inline error tied to the retry button, not silence', async () => {
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => {});
    mocks.completeTrailTask.mockRejectedValueOnce(new Error('network down'));

    renderChores();

    const button = await findDoItButton();
    button.focus();
    fireEvent.click(button);

    const alert = await screen.findByRole('alert');
    // The underlying cause is surfaced, not a one-size-fits-all string
    // (finding 5) — and logged, so a real failure leaves a diagnostic trail
    // instead of vanishing.
    expect(alert).toHaveTextContent('network down');
    expect(consoleError).toHaveBeenCalledWith(
      expect.stringContaining('water_the_beds'),
      expect.any(Error)
    );

    // The row stays actionable: no false "done" state, the button is
    // enabled again so the user can retry rather than seeing a dead
    // control, and focus never left it (finding 1).
    const retryButton = await screen.findByRole('button', {
      name: 'Try again',
    });
    expect(retryButton).toBe(button);
    expect(retryButton).not.toBeDisabled();
    expect(document.activeElement).toBe(retryButton);

    // The error is associated with the control it explains, not just an
    // unconnected sibling paragraph (finding 4).
    expect(retryButton).toHaveAttribute('aria-describedby', alert.id);

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

    consoleError.mockRestore();
  });

  it('shows a distinct message for an expired session (401) rather than a generic failure', async () => {
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => {});
    const unauthorized = Object.assign(new Error('HTTP 401 - Unauthorized'), {
      status: 401,
    });
    mocks.completeTrailTask.mockRejectedValueOnce(unauthorized);

    renderChores();

    const button = await findDoItButton();
    fireEvent.click(button);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /session has expired/i
    );

    consoleError.mockRestore();
  });

  it('calls completeTrailTask exactly once with the correct chore id per click', async () => {
    mocks.completeTrailTask.mockResolvedValue({
      tasks: [{ ...UNMAPPED_TASK, completed: true }],
      xp: 110,
      streak: 0,
      daily_totals: {},
      today: '2026-08-24',
    });

    renderChores();

    const button = await findDoItButton();
    fireEvent.click(button);

    // Wait for the completion to settle and the button to show "Done".
    await screen.findByRole('button', { name: 'Done' });

    // The core regression assertion: exactly one API call per click.
    expect(mocks.completeTrailTask).toHaveBeenCalledTimes(1);

    // The call must carry the clicked chore's id — and only that id.
    expect(mocks.completeTrailTask).toHaveBeenCalledWith(
      'water_the_beds',
      expect.anything()
    );

    // No other chore ids may be passed (e.g., from a sibling row or a
    // stale closure over a different task).
    expect(mocks.completeTrailTask).not.toHaveBeenCalledWith(
      'research_new_stock',
      expect.anything()
    );
    expect(mocks.completeTrailTask).not.toHaveBeenCalledWith(
      'review_portfolio',
      expect.anything()
    );
  });
});
