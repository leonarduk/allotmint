import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RebalancePlan, Strategy, StrategyList } from '@/types';

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetRebalancePlan = vi.hoisted(() => vi.fn());
const mockSaveAllocationPolicy = vi.hoisted(() => vi.fn());
const mockGetNewCashPlan = vi.hoisted(() => vi.fn());
const mockGetStrategies = vi.hoisted(() => vi.fn());
const mockApplyStrategy = vi.hoisted(() => vi.fn());
const mockCreateStrategy = vi.hoisted(() => vi.fn());
const mockUpdateStrategy = vi.hoisted(() => vi.fn());
const mockDeleteStrategy = vi.hoisted(() => vi.fn());
const mockDuplicateStrategy = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getOwners: mockGetOwners,
  getRebalancePlan: mockGetRebalancePlan,
  saveAllocationPolicy: mockSaveAllocationPolicy,
  getNewCashPlan: mockGetNewCashPlan,
  getStrategies: mockGetStrategies,
  applyStrategy: mockApplyStrategy,
  createStrategy: mockCreateStrategy,
  updateStrategy: mockUpdateStrategy,
  deleteStrategy: mockDeleteStrategy,
  duplicateStrategy: mockDuplicateStrategy,
}));

vi.mock('@/RouteContext', () => ({
  useRoute: () => ({
    mode: 'rebalance',
    setMode: vi.fn(),
    selectedOwner: '',
    setSelectedOwner: vi.fn(),
    selectedGroup: '',
    setSelectedGroup: vi.fn(),
  }),
}));

function makePlan(overrides: Partial<RebalancePlan> = {}): RebalancePlan {
  return {
    policy: { targets: { equity: 60, bond: 40 }, tolerance_pct: 5 },
    total_value: 2000,
    classes: [
      {
        asset_class: 'equity',
        label: 'Equity',
        current_value: 1600,
        current_pct: 80,
        target_pct: 60,
        drift_pct: 20,
        in_band: false,
      },
      {
        asset_class: 'bond',
        label: 'Bond',
        current_value: 400,
        current_pct: 20,
        target_pct: 40,
        drift_pct: -20,
        in_band: false,
      },
    ],
    unclassified_value: 0,
    unclassified_pct: 0,
    unpriced_tickers: [],
    accounts: [
      { id: 'isa', label: 'ISA', value: 1000, cash: 0 },
      { id: 'sipp', label: 'SIPP', value: 1000, cash: 0 },
    ],
    trades: [
      {
        account_id: 'isa',
        account: 'ISA',
        asset_class: 'equity',
        action: 'sell',
        amount: 200,
        ticker: 'EQ1',
        name: 'Equity One',
      },
      {
        account_id: 'isa',
        account: 'ISA',
        asset_class: 'bond',
        action: 'buy',
        amount: 200,
        ticker: 'BD1',
        name: 'Bond One',
      },
      {
        account_id: 'sipp',
        account: 'SIPP',
        asset_class: 'equity',
        action: 'sell',
        amount: 200,
        ticker: 'EQ2',
        name: null,
      },
      {
        account_id: 'sipp',
        account: 'SIPP',
        asset_class: 'bond',
        action: 'buy',
        amount: 200,
        ticker: null,
        name: null,
      },
    ],
    unfunded_amount: 0,
    notes: [],
    ...overrides,
  };
}

const GB_50_50: Strategy = {
  id: 'golden_butterfly_no_scv_50_50',
  name: 'Golden Butterfly without small-value, 50/50 gilts',
  description: 'The Golden Butterfly without small-cap value.',
  source: 'Variant of the Portfolio Charts Golden Butterfly.',
  uk_mapping: 'Long, intermediate and short gilts.',
  targets: {
    equity: 40,
    long_gilts: 10,
    intermediate_gilts: 10,
    short_gilts: 20,
    gold: 20,
  },
  builtin: true,
};

const MINE: Strategy = {
  id: 'user-abc',
  name: 'Mine',
  description: '',
  source: '',
  uk_mapping: '',
  targets: { equity: 60, bond: 40 },
  builtin: false,
};

function makeStrategies(overrides: Partial<StrategyList> = {}): StrategyList {
  return { strategies: [GB_50_50, MINE], active: null, ...overrides };
}

async function renderPage() {
  const { default: Strategy } = await import('@/pages/Strategy');
  render(<Strategy />, { wrapper: MemoryRouter });
  await waitFor(() =>
    expect(mockGetRebalancePlan).toHaveBeenCalledWith('alex')
  );
}

const strategyRow = async (name: string) =>
  (
    await within(
      await screen.findByRole('region', { name: 'Strategies' })
    ).findByText(name, { selector: 'span' })
  ).closest('li') as HTMLElement;

describe('Strategy page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    mockGetOwners.mockResolvedValue([{ owner: 'alex', accounts: [] }]);
    mockGetRebalancePlan.mockResolvedValue(makePlan());
    mockGetStrategies.mockResolvedValue(makeStrategies());
  });

  it('is titled Strategy', async () => {
    await renderPage();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Strategy' })
    ).toBeInTheDocument();
  });

  it('lists built-in and custom strategies; built-ins cannot be edited or deleted', async () => {
    await renderPage();
    const builtin = await strategyRow(GB_50_50.name);
    expect(within(builtin).getByText('Built-in')).toBeInTheDocument();
    const edit = within(builtin).getByRole('button', {
      name: `Edit ${GB_50_50.name}`,
    });
    expect(edit).toBeDisabled();
    expect(edit.parentElement).toHaveAttribute(
      'title',
      expect.stringMatching(/read-only/)
    );
    expect(
      within(builtin).getByRole('button', { name: `Delete ${GB_50_50.name}` })
    ).toBeDisabled();
    expect(
      within(builtin).getByText(/Equity 40% · Long gilts 10%/)
    ).toBeInTheDocument();

    const mine = await strategyRow('Mine');
    expect(within(mine).getByText('Custom')).toBeInTheDocument();
    expect(
      within(mine).getByRole('button', { name: 'Edit Mine' })
    ).toBeEnabled();
  });

  it('applies a strategy after confirming it replaces custom targets, then reloads', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockApplyStrategy.mockResolvedValue({});
    await renderPage();
    const row = await strategyRow(GB_50_50.name);
    fireEvent.click(
      within(row).getByRole('button', { name: `Apply ${GB_50_50.name}` })
    );
    expect(confirm).toHaveBeenCalled();
    await waitFor(() =>
      expect(mockApplyStrategy).toHaveBeenCalledWith('alex', GB_50_50.id)
    );
    await waitFor(() => expect(mockGetRebalancePlan).toHaveBeenCalledTimes(2));
    expect(mockGetStrategies).toHaveBeenCalledTimes(2);
    expect(
      await screen.findByText(`Applied ${GB_50_50.name}.`)
    ).toBeInTheDocument();
  });

  it('does not apply when the replacement is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    await renderPage();
    const row = await strategyRow(GB_50_50.name);
    fireEvent.click(
      within(row).getByRole('button', { name: `Apply ${GB_50_50.name}` })
    );
    expect(mockApplyStrategy).not.toHaveBeenCalled();
  });

  it('shows the active strategy and flags modified targets', async () => {
    mockGetStrategies.mockResolvedValue(
      makeStrategies({
        active: {
          id: GB_50_50.id,
          name: GB_50_50.name,
          builtin: true,
          exists: true,
          applied_targets: GB_50_50.targets,
          applied_at: '2026-10-06T10:00:00+00:00',
          modified: true,
          strategy_changed: false,
        },
      })
    );
    await renderPage();
    const status = await screen.findByLabelText('Active strategy');
    expect(status).toHaveTextContent(`Active strategy: ${GB_50_50.name}`);
    expect(within(status).getByText('Modified')).toBeInTheDocument();
    const row = await strategyRow(GB_50_50.name);
    expect(within(row).getByText('Active')).toBeInTheDocument();
  });

  it('labels targets that came from no strategy as custom', async () => {
    await renderPage();
    expect(await screen.findByLabelText('Active strategy')).toHaveTextContent(
      'Custom'
    );
  });

  it('duplicates a built-in into an editable copy and saves edits', async () => {
    const copy = {
      ...GB_50_50,
      id: 'user-copy',
      name: `Copy of ${GB_50_50.name}`,
      builtin: false,
    };
    mockDuplicateStrategy.mockResolvedValue(copy);
    mockUpdateStrategy.mockResolvedValue(copy);
    await renderPage();
    const row = await strategyRow(GB_50_50.name);
    fireEvent.click(
      within(row).getByRole('button', { name: `Duplicate ${GB_50_50.name}` })
    );
    await waitFor(() =>
      expect(mockDuplicateStrategy).toHaveBeenCalledWith('alex', GB_50_50.id)
    );
    const editor = await screen.findByRole('form', {
      name: `Edit ${copy.name}`,
    });
    // The copy's gilt split opens Bond by sub-class.
    expect(
      within(editor).getByLabelText('Strategy % for Long gilts')
    ).toHaveValue(10);
    fireEvent.change(within(editor).getByLabelText('Strategy % for Equity'), {
      target: { value: '30' },
    });
    fireEvent.change(within(editor).getByLabelText('Strategy % for Gold'), {
      target: { value: '30' },
    });
    fireEvent.click(
      within(editor).getByRole('button', { name: 'Save strategy' })
    );
    await waitFor(() =>
      expect(mockUpdateStrategy).toHaveBeenCalledWith('alex', 'user-copy', {
        name: copy.name,
        description: copy.description,
        targets: {
          equity: 30,
          long_gilts: 10,
          intermediate_gilts: 10,
          short_gilts: 20,
          gold: 30,
        },
      })
    );
  });

  it('creates a new strategy split by equity sub-class', async () => {
    mockCreateStrategy.mockResolvedValue({ ...MINE, id: 'user-new' });
    await renderPage();
    fireEvent.click(
      await screen.findByRole('button', { name: 'New strategy' })
    );
    const editor = await screen.findByRole('form', { name: 'New strategy' });
    const save = within(editor).getByRole('button', { name: 'Save strategy' });
    expect(save).toBeDisabled();
    fireEvent.change(within(editor).getByLabelText('Name'), {
      target: { value: 'Tilted' },
    });
    fireEvent.click(
      within(editor).getByRole('button', { name: 'Split Equity by sub-class' })
    );
    fireEvent.change(
      within(editor).getByLabelText('Strategy % for Broad equity'),
      {
        target: { value: '80' },
      }
    );
    fireEvent.change(
      within(editor).getByLabelText('Strategy % for Small-cap value'),
      { target: { value: '20' } }
    );
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() =>
      expect(mockCreateStrategy).toHaveBeenCalledWith('alex', {
        name: 'Tilted',
        description: '',
        targets: { broad_equity: 80, small_cap_value: 20 },
      })
    );
    await waitFor(() =>
      expect(
        screen.queryByRole('form', { name: 'New strategy' })
      ).not.toBeInTheDocument()
    );
  });

  it('deletes a user strategy after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockDeleteStrategy.mockResolvedValue({ status: 'deleted', id: MINE.id });
    await renderPage();
    const row = await strategyRow('Mine');
    fireEvent.click(within(row).getByRole('button', { name: 'Delete Mine' }));
    await waitFor(() =>
      expect(mockDeleteStrategy).toHaveBeenCalledWith('alex', MINE.id)
    );
  });

  it('reports a failed action without losing the list', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockApplyStrategy.mockRejectedValue(new Error('nope'));
    await renderPage();
    const row = await strategyRow('Mine');
    fireEvent.click(within(row).getByRole('button', { name: 'Apply Mine' }));
    expect(await screen.findByText('nope')).toBeInTheDocument();
    expect(await strategyRow(GB_50_50.name)).toBeInTheDocument();
  });

  it('reports strategy load failures', async () => {
    mockGetStrategies.mockRejectedValue(new Error('down'));
    await renderPage();
    expect(
      await screen.findByText(/Unable to load strategies for alex: down/)
    ).toBeInTheDocument();
  });

  it('shows per-class drift against stored targets without any input', async () => {
    await renderPage();
    const drift = await screen.findByRole('region', {
      name: 'Allocation drift',
    });
    const equityRow = within(drift)
      .getByText('Equity')
      .closest('tr') as HTMLElement;
    expect(within(equityRow).getByText('80.00%')).toBeInTheDocument();
    expect(within(equityRow).getByText('60.00%')).toBeInTheDocument();
    expect(within(equityRow).getByText('+20.00')).toBeInTheDocument();
    expect(within(equityRow).getByText('Overweight')).toBeInTheDocument();
    const bondRow = within(drift)
      .getByText('Bond')
      .closest('tr') as HTMLElement;
    expect(within(bondRow).getByText('Underweight')).toBeInTheDocument();
  });

  it('groups suggested trades by account', async () => {
    await renderPage();
    const trades = await screen.findByRole('region', {
      name: 'Suggested trades',
    });
    expect(
      within(trades).getByRole('heading', { name: 'ISA' })
    ).toBeInTheDocument();
    expect(
      within(trades).getByRole('heading', { name: 'SIPP' })
    ).toBeInTheDocument();
    expect(within(trades).getAllByText('SELL')).toHaveLength(2);
    expect(
      within(trades).getByText('Choose an instrument')
    ).toBeInTheDocument();
  });

  it('names suggested instruments and links them to their research page', async () => {
    await renderPage();
    const trades = await screen.findByRole('region', {
      name: 'Suggested trades',
    });
    const named = within(trades).getByRole('link', { name: /Equity One/ });
    expect(named).toHaveAttribute('href', '/research/EQ1');
    expect(named).toHaveTextContent('Equity One (EQ1)');
    // Without a name the ticker alone is the link text.
    expect(within(trades).getByRole('link', { name: 'EQ2' })).toHaveAttribute(
      'href',
      '/research/EQ2'
    );
    expect(within(trades).getAllByRole('link')).toHaveLength(3);
  });

  it('shows an empty state when every class is in band', async () => {
    mockGetRebalancePlan.mockResolvedValue(makePlan({ trades: [] }));
    await renderPage();
    expect(await screen.findByText(/No trades required/)).toBeInTheDocument();
  });

  it('shows the unclassified bucket and notes', async () => {
    mockGetRebalancePlan.mockResolvedValue(
      makePlan({
        unclassified_value: 250,
        unclassified_pct: 12.5,
        notes: ['£250.00 (12.50%) is in holdings with no asset class.'],
      })
    );
    await renderPage();
    expect(await screen.findByText('Unclassified')).toBeInTheDocument();
    expect(screen.getByText('Needs an asset class')).toBeInTheDocument();
    expect(
      screen.getByText(/is in holdings with no asset class/)
    ).toBeInTheDocument();
  });

  it('prompts for targets and hides trades when no policy is stored', async () => {
    mockGetRebalancePlan.mockResolvedValue(
      makePlan({ policy: { targets: {}, tolerance_pct: 5 }, trades: [] })
    );
    await renderPage();
    expect(
      await screen.findByText(/save target allocations/)
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('region', { name: 'Suggested trades' })
    ).not.toBeInTheDocument();
  });

  it('only enables saving when targets total 100% and saves the parsed policy', async () => {
    mockSaveAllocationPolicy.mockResolvedValue({
      targets: { equity: 70, bond: 30 },
      tolerance_pct: 3,
    });
    await renderPage();
    const equity = await screen.findByLabelText('Target % for Equity');
    const save = screen.getByRole('button', { name: 'Save targets' });
    expect(save).toBeEnabled();

    fireEvent.change(equity, { target: { value: '70' } });
    expect(save).toBeDisabled();
    expect(screen.getByText(/must equal 100%/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Target % for Bond'), {
      target: { value: '30' },
    });
    fireEvent.change(screen.getByLabelText(/Tolerance band/), {
      target: { value: '3' },
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() =>
      expect(mockSaveAllocationPolicy).toHaveBeenCalledWith('alex', {
        targets: { equity: 70, bond: 30 },
        tolerance_pct: 3,
      })
    );
    await waitFor(() => expect(mockGetRebalancePlan).toHaveBeenCalledTimes(2));
  });

  it('can start the target editor from the current allocation', async () => {
    await renderPage();
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Start from current allocation',
      })
    );
    expect(screen.getByLabelText('Target % for Equity')).toHaveValue(80);
    expect(screen.getByLabelText('Target % for Bond')).toHaveValue(20);
  });

  it('plans a buy-only contribution into the chosen account', async () => {
    mockGetNewCashPlan.mockResolvedValue({
      account_id: 'sipp',
      account: 'SIPP',
      trades: [
        {
          account_id: 'sipp',
          account: 'SIPP',
          asset_class: 'bond',
          action: 'buy',
          amount: 500,
          ticker: 'BD2',
          name: 'Bond Two',
        },
      ],
      keep_as_cash: 0,
    });
    await renderPage();
    const form = await screen.findByRole('form', { name: 'Invest new cash' });
    fireEvent.change(within(form).getByLabelText('Amount (£)'), {
      target: { value: '500' },
    });
    fireEvent.change(within(form).getByLabelText('Into account'), {
      target: { value: 'sipp' },
    });
    fireEvent.click(
      within(form).getByRole('button', { name: 'Plan contribution' })
    );

    await waitFor(() =>
      expect(mockGetNewCashPlan).toHaveBeenCalledWith('alex', 500, 'sipp')
    );
    expect(
      await within(form).findByRole('link', { name: /Bond Two/ })
    ).toHaveAttribute('href', '/research/BD2');
    expect(within(form).queryByText('SELL')).not.toBeInTheDocument();
  });

  it('splits Bond into sub-classes and saves sub-class targets', async () => {
    mockSaveAllocationPolicy.mockResolvedValue({
      targets: { equity: 60, long_gilts: 15, short_gilts: 25 },
      tolerance_pct: 5,
    });
    await renderPage();
    const split = await screen.findByRole('button', {
      name: 'Split Bond by sub-class',
    });
    expect(split).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(split);

    expect(
      screen.queryByLabelText('Target % for Bond')
    ).not.toBeInTheDocument();
    const save = screen.getByRole('button', { name: 'Save targets' });
    expect(save).toBeDisabled(); // 60% until sub-classes are filled in
    fireEvent.change(screen.getByLabelText('Target % for Long gilts'), {
      target: { value: '15' },
    });
    fireEvent.change(
      screen.getByLabelText('Target % for Short gilts / ultrashort'),
      { target: { value: '25' } }
    );
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() =>
      expect(mockSaveAllocationPolicy).toHaveBeenCalledWith('alex', {
        targets: { equity: 60, long_gilts: 15, short_gilts: 25 },
        tolerance_pct: 5,
      })
    );
  });

  it('opens split classes and shows sub-class drift rows from a sub-class policy', async () => {
    mockGetRebalancePlan.mockResolvedValue(
      makePlan({
        policy: {
          targets: { equity: 60, long_gilts: 30, gold: 10 },
          tolerance_pct: 5,
        },
        classes: [
          {
            asset_class: 'equity',
            parent: null,
            label: 'Equity',
            current_value: 1200,
            current_pct: 60,
            target_pct: 60,
            drift_pct: 0,
            in_band: true,
          },
          {
            asset_class: 'long_gilts',
            parent: 'bond',
            label: 'Long gilts',
            current_value: 600,
            current_pct: 30,
            target_pct: 30,
            drift_pct: 0,
            in_band: true,
          },
          {
            asset_class: 'bond',
            parent: 'bond',
            label: 'Bond — no sub-class',
            current_value: 200,
            current_pct: 10,
            target_pct: null,
            drift_pct: null,
            in_band: null,
          },
        ],
        sub_classes: [
          {
            asset_class: 'long_gilts',
            parent: 'bond',
            label: 'Long gilts',
            current_value: 600,
            current_pct: 30,
          },
          {
            asset_class: 'bond',
            parent: 'bond',
            label: 'Bond — no sub-class',
            current_value: 200,
            current_pct: 10,
          },
        ],
        trades: [
          {
            account_id: '0',
            account: 'ISA',
            asset_class: 'gold',
            action: 'buy',
            amount: 100,
            ticker: 'PHGP.L',
          },
        ],
      })
    );
    await renderPage();
    const drift = await screen.findByRole('region', {
      name: 'Allocation drift',
    });
    expect(within(drift).getByText('Bond › Long gilts')).toBeInTheDocument();
    const unresolved = within(drift)
      .getByText('Bond — no sub-class')
      .closest('tr') as HTMLElement;
    expect(
      within(unresolved).getByText('Needs a sub-class')
    ).toBeInTheDocument();

    expect(
      screen.getByRole('button', { name: 'Combine Bond sub-classes' })
    ).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('Target % for Long gilts')).toHaveValue(30);
    expect(screen.getByLabelText('Target % for Gold')).toHaveValue(10);
    expect(screen.getByText('Total: 100.00%')).toBeInTheDocument();

    const trades = screen.getByRole('region', { name: 'Suggested trades' });
    expect(within(trades).getByText('Gold')).toBeInTheDocument();
  });

  it('keeps the chosen account when the plan reloads with accounts reordered (#9496)', async () => {
    const plan = makePlan();
    // Saving targets reloads the plan; the backend may list accounts in a
    // different order, so the selection must follow the account id, not its
    // position in the list.
    mockGetRebalancePlan.mockResolvedValueOnce(plan).mockResolvedValueOnce({
      ...plan,
      accounts: [...plan.accounts].reverse(),
    });
    mockSaveAllocationPolicy.mockResolvedValue(plan.policy);
    mockGetNewCashPlan.mockResolvedValue({
      account_id: 'sipp',
      account: 'SIPP',
      trades: [],
      keep_as_cash: 100,
    });
    await renderPage();
    const form = await screen.findByRole('form', { name: 'Invest new cash' });
    const select = within(form).getByLabelText(
      'Into account'
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'sipp' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save targets' }));
    await waitFor(() => expect(mockGetRebalancePlan).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(within(select).getAllByRole('option')[0]).toHaveTextContent('SIPP')
    );

    expect(select.value).toBe('sipp');
    expect(select.selectedOptions[0]).toHaveTextContent('SIPP');
    fireEvent.change(within(form).getByLabelText('Amount (£)'), {
      target: { value: '100' },
    });
    fireEvent.click(
      within(form).getByRole('button', { name: 'Plan contribution' })
    );
    await waitFor(() =>
      expect(mockGetNewCashPlan).toHaveBeenCalledWith('alex', 100, 'sipp')
    );
  });

  it('falls back to the first account if the chosen one disappears from a reloaded plan', async () => {
    const plan = makePlan();
    mockGetRebalancePlan.mockResolvedValueOnce(plan).mockResolvedValueOnce({
      ...plan,
      accounts: plan.accounts.filter((a) => a.id !== 'sipp'),
    });
    mockSaveAllocationPolicy.mockResolvedValue(plan.policy);
    mockGetNewCashPlan.mockResolvedValue({
      account_id: 'isa',
      account: 'ISA',
      trades: [],
      keep_as_cash: 100,
    });
    await renderPage();
    const form = await screen.findByRole('form', { name: 'Invest new cash' });
    const select = within(form).getByLabelText(
      'Into account'
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'sipp' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save targets' }));
    await waitFor(() => expect(select.value).toBe('isa'));

    fireEvent.change(within(form).getByLabelText('Amount (£)'), {
      target: { value: '100' },
    });
    fireEvent.click(
      within(form).getByRole('button', { name: 'Plan contribution' })
    );
    await waitFor(() =>
      expect(mockGetNewCashPlan).toHaveBeenCalledWith('alex', 100, 'isa')
    );
  });

  it('reports plan load failures', async () => {
    mockGetRebalancePlan.mockRejectedValue(new Error('boom'));
    const { default: Strategy } = await import('@/pages/Strategy');
    render(<Strategy />, { wrapper: MemoryRouter });
    expect(
      await screen.findByText(/Unable to load rebalance plan for alex: boom/)
    ).toBeInTheDocument();
  });
});
