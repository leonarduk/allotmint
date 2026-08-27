import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigationType,
} from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Portfolio } from '@/types';

/**
 * Covers the grower-picker/group-membership fix (#7189) and the routing
 * fixes (#7192): the picker filtering to grouped owners, the /groups
 * failure/empty/no-intersection fallbacks, the ?owner=demo deep link both
 * loading its data *and* being correctly represented in the picker itself,
 * the not-found panel on an unknown /plot/* path, and the URL round-trip
 * (via a real history.replace, not push) when a different grower is chosen.
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

/**
 * Surfaces the router's own idea of the current URL and how it got there
 * (`useNavigationType`: 'POP' | 'PUSH' | 'REPLACE'), so tests can assert on
 * what actually reached the URL/history stack instead of re-reading the
 * `<select>` they just changed — which would pass identically against the
 * pre-#7192 local-state-only implementation and prove nothing.
 */
function LocationProbe() {
  const location = useLocation();
  const navType = useNavigationType();
  return (
    <div
      data-testid="location-probe"
      data-search={location.search}
      data-nav-type={navType}
    />
  );
}

function renderPlot(path = '/plot') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LocationProbe />
      <Routes>
        <Route path="/plot/*" element={<PlotApp />} />
      </Routes>
    </MemoryRouter>
  );
}

function probe() {
  return screen.getByTestId('location-probe');
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

  it('falls back to every owner when configured group members match none of the current owners', async () => {
    mocks.getGroups.mockResolvedValue([
      { slug: 'other-house', name: 'Someone else', members: ['nobody', 'ghost'] },
    ]);
    renderPlot();

    const picker = await screen.findByLabelText('Grower');
    const optionLabels = Array.from(picker.querySelectorAll('option')).map(
      (opt) => opt.textContent
    );
    expect(optionLabels).toContain('Demo Account');
    expect(optionLabels).toHaveLength(4);
  });

  it('does not show the picker until /groups settles, so the unfiltered list (demo included) never flashes on screen', async () => {
    let resolveGroups: (value: typeof GROUPS) => void = () => {};
    mocks.getGroups.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveGroups = resolve;
        })
    );
    renderPlot();

    // The default owner's portfolio has already loaded (so the picker would
    // render now if it were going to), but /groups is still pending.
    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalled());
    expect(screen.queryByLabelText('Grower')).toBeNull();
    expect(screen.queryByText('Demo Account')).toBeNull();

    resolveGroups(GROUPS);
    await waitFor(() =>
      expect(screen.getByLabelText('Grower')).toBeInTheDocument()
    );
    expect(screen.queryByText('Demo Account')).toBeNull();
  });

  it('shows the demo account as the selected, addressable picker option when deep-linked, without adding it back permanently', async () => {
    renderPlot('/plot?owner=demo');

    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledWith('demo'));

    const picker = (await screen.findByLabelText('Grower')) as HTMLSelectElement;
    // The regression this guards: with a filtered option list and no
    // matching <option>, the browser silently reselects whichever option is
    // first (e.g. Alex) while demo's data stays on screen underneath.
    // Asserting the select's own resolved value/selected option is what
    // catches that — asserting only that "Demo Account" text is absent
    // elsewhere on the page would not.
    expect(picker.value).toBe('demo');
    const selected = picker.options[picker.selectedIndex];
    expect(selected.value).toBe('demo');
    expect(selected.textContent).toBe('Demo Account');

    // Switching to a grouped grower drops demo back out of the option list.
    fireEvent.change(picker, { target: { value: 'alex' } });
    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledWith('alex'));
    const labelsAfter = Array.from(picker.querySelectorAll('option')).map(
      (opt) => opt.textContent
    );
    expect(labelsAfter).not.toContain('Demo Account');
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

  it('writes the chosen grower to the URL via history.replace, not push', async () => {
    renderPlot();

    await screen.findByLabelText('Grower');
    fireEvent.change(screen.getByLabelText('Grower'), {
      target: { value: 'alex' },
    });

    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledWith('alex'));
    await waitFor(() => expect(probe().dataset.search).toBe('?owner=alex'));
    // The explicit #7192 constraint: a grower change must not push a new
    // history entry.
    expect(probe().dataset.navType).toBe('REPLACE');
  });

  it('a grower change written to the URL is what a fresh mount at that URL reads back (survives a refresh)', async () => {
    const { unmount } = renderPlot();

    await screen.findByLabelText('Grower');
    fireEvent.change(screen.getByLabelText('Grower'), {
      target: { value: 'alex' },
    });
    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledWith('alex'));
    const searchAfterChange = probe().dataset.search;
    expect(searchAfterChange).toBe('?owner=alex');

    // A hard refresh discards all in-memory React/router state and re-reads
    // only the URL. Unmounting and mounting a fresh instance at that same
    // URL emulates that; re-reading the already-changed <select> in place
    // (the old, weaker version of this test) would pass even if the value
    // never left local component state.
    unmount();
    mocks.getPortfolio.mockClear();
    renderPlot(`/plot${searchAfterChange}`);

    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledWith('alex'));
    const select = (await screen.findByLabelText('Grower')) as HTMLSelectElement;
    expect(select.value).toBe('alex');
  });

  it('deep-linking ?owner=joe still selects joe', async () => {
    renderPlot('/plot?owner=joe');

    await waitFor(() => expect(mocks.getPortfolio).toHaveBeenCalledWith('joe'));
  });
});
