import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RebalancePlan } from '@/types';

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetRebalancePlan = vi.hoisted(() => vi.fn());
const mockSaveAllocationPolicy = vi.hoisted(() => vi.fn());
const mockGetNewCashPlan = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getOwners: mockGetOwners,
  getRebalancePlan: mockGetRebalancePlan,
  saveAllocationPolicy: mockSaveAllocationPolicy,
  getNewCashPlan: mockGetNewCashPlan,
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
      { id: '0', label: 'ISA', value: 1000, cash: 0 },
      { id: '1', label: 'SIPP', value: 1000, cash: 0 },
    ],
    trades: [
      {
        account_id: '0',
        account: 'ISA',
        asset_class: 'equity',
        action: 'sell',
        amount: 200,
        ticker: 'EQ1',
        name: 'Equity One',
      },
      {
        account_id: '0',
        account: 'ISA',
        asset_class: 'bond',
        action: 'buy',
        amount: 200,
        ticker: 'BD1',
        name: 'Bond One',
      },
      {
        account_id: '1',
        account: 'SIPP',
        asset_class: 'equity',
        action: 'sell',
        amount: 200,
        ticker: 'EQ2',
        name: null,
      },
      {
        account_id: '1',
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

async function renderPage() {
  const { default: Rebalance } = await import('@/pages/Rebalance');
  render(<Rebalance />, { wrapper: MemoryRouter });
  await waitFor(() =>
    expect(mockGetRebalancePlan).toHaveBeenCalledWith('alex')
  );
}

describe('Rebalance page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetOwners.mockResolvedValue([{ owner: 'alex', accounts: [] }]);
    mockGetRebalancePlan.mockResolvedValue(makePlan());
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
      await screen.findByText(/Save target allocations/)
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
      account_id: '1',
      account: 'SIPP',
      trades: [
        {
          account_id: '1',
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
      target: { value: '1' },
    });
    fireEvent.click(
      within(form).getByRole('button', { name: 'Plan contribution' })
    );

    await waitFor(() =>
      expect(mockGetNewCashPlan).toHaveBeenCalledWith('alex', 500, '1')
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

  it('reports plan load failures', async () => {
    mockGetRebalancePlan.mockRejectedValue(new Error('boom'));
    const { default: Rebalance } = await import('@/pages/Rebalance');
    render(<Rebalance />, { wrapper: MemoryRouter });
    expect(
      await screen.findByText(/Unable to load rebalance plan for alex: boom/)
    ).toBeInTheDocument();
  });
});
