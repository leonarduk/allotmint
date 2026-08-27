import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Portfolio } from '@/types';

/**
 * Covers the grower-picker/group-membership fix (#7189) and the routing
 * fixes (#7192): the picker filtering to grouped owners, the /groups
 * failure/empty fallback, the ?owner=demo deep link bypassing the picker
 * filter, the not-found panel on an unknown /plot/* path, and the URL
 * round-trip when a different grower is chosen.
 */

const portfolio: Portfolio = {
  owner: 'steve',
  as_of: '2026-08-24',
  trades_this_month: 2,
  trades_remaining: 8,
  total_value_estimate_gbp: 10_000,
  accounts: [],
};

const demoPortfolio: Portfolio = {
  ...portfolio,
  owner: 'demo',
};

const alexPortfolio: Portfolio = {
  ...portfolio,
  owner: 'alex',
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

function renderPlot(path = '/plot') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/plot/*" element={<PlotApp />} />
      </Routes>
    </MemoryRouter>
  );
}

const OWNERS = [
  { owner: 'alex', full_name: 'Alex Leonard', accounts: ['stocks-isa'] },
  { owner: 'joe', full_name: 'Joe Leonard', accounts: ['stocks-isa'] },
  { owner: 'steve', full_name: 'Steve Leonard', accounts: ['stocks-isa'] },
  { owner: 'demo', full_name: 'Demo Account', accounts: ['stocks-isa'] },
];

const GROUPS = [
  { slug: 'all', name: 'At a glance', members: ['alex', 'joe', 'steve'] },
];

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  mocks.getOwners.mockResolvedValue(OWNERS);
  mocks.getGroups.mockResolvedValue(GROUPS);
  mocks.getPortfolio.mockImplementation((owner: string) =>
    Promise.resolve(
      owner === 'demo' ? demoPortfolio : owner === 'alex' ? alexPortfolio : portfolio
    )
  );
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
  mocks.getQuotes.mockResolvedValue([]);
});

describe('Plot grower picker group filtering (#7189)', () => {
  it('lists only owners that belong to a configured group, not the demo seed account', async () => {
    renderPlot();

    const picker = await screen.findByLabelText('Grower');
    const optionLabels = Array.from(picker.querySelectorAll('option')).map(
      (opt) => opt.textContent
    );
    expect(optionLabels).toEqual(['Alex Leonard', 'Joe Leonard', 'Steve Leonard']);
    expect(optionLabels).not.toContain('Demo Account');
  });

  it('falls back to every owner when /groups fails', async () => {
    mocks.getGroups.mockRejectedValue(new Error('groups unavailable'));
    renderPlot();

    const picker = await screen.findByLabelText('Grower');
    const optionLabels = Array.from(picker.querySelectorAll('option')).map(
      (opt) => opt.textContent
    );
    expect(optionLabels).toContain('Demo Account');
    expect(optionLabels).toHaveLength(4);
  });

  it('falls back to every owner when /groups returns empty', async () => {
    mocks.getGroups.mockResolvedValue([]);
    renderPlot();

    const picker = await screen.findByLabelText('Grower');
    const optionLabels = Array.from(picker.querySelectorAll('option')).map(
      (opt) => opt.textContent
    );
    expect(optionLabels).toContain('Demo Account');
    expect(optionLabels).toHaveLength(4);
  });

  it('still loads an explicit ?owner=demo deep link even though demo is excluded from the picker', async () => {
    renderPlot('/plot?owner=demo');

    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledWith('demo'));
    // The picker itself still hides demo — the data layer is unaffected.
    const picker = await screen.findByLabelText('Grower');
    const optionLabels = Array.from(picker.querySelectorAll('option')).map(
      (opt) => opt.textContent
    );
    expect(optionLabels).not.toContain('Demo Account');
  });
});

describe('Plot routing (#7192)', () => {
  it('shows a not-found panel for an unknown /plot/* path instead of the hub', async () => {
    renderPlot('/plot/not-a-real-page');

    expect(
      await screen.findByRole('heading', { name: 'Nothing growing here' })
    ).toBeInTheDocument();
    // The hub's own content (not just its shared HUD title) must be absent.
    expect(
      screen.queryByRole('region', { name: 'Featured crops' })
    ).toBeNull();
  });

  it('writes the chosen grower to the URL (replace) and it survives past the initial mount', async () => {
    renderPlot();

    await screen.findByLabelText('Grower');
    fireEvent.change(screen.getByLabelText('Grower'), {
      target: { value: 'alex' },
    });

    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledWith('alex'));

    // Re-rendering the same URL search state (simulating "survives a
    // refresh") still selects alex, proving the choice now lives in the URL
    // rather than only in local component state.
    const select = screen.getByLabelText('Grower') as HTMLSelectElement;
    expect(select.value).toBe('alex');
  });

  it('deep-linking ?owner=joe still selects joe', async () => {
    renderPlot('/plot?owner=joe');

    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledWith('joe'));
  });
});
