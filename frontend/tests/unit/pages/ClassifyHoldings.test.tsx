import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  RebalancePlan,
  RebalanceSleeveRow,
  UnclassifiedHolding,
} from '@/types';
import ClassifyHoldings from '@/pages/ClassifyHoldings';

const mockGetRebalancePlan = vi.hoisted(() => vi.fn());
const mockSetInstrumentAssetClass = vi.hoisted(() => vi.fn());
const mockRoute = vi.hoisted(() => ({ selectedOwner: '' }));

vi.mock('@/api', () => ({
  getRebalancePlan: mockGetRebalancePlan,
  setInstrumentAssetClass: mockSetInstrumentAssetClass,
}));

vi.mock('@/RouteContext', () => ({
  useRoute: () => mockRoute,
}));

const QQQ: UnclassifiedHolding = {
  ticker: 'QQQ.N',
  symbol: 'QQQ',
  exchange: 'N',
  name: 'Invesco QQQ',
  value: 250,
};
const BARE: UnclassifiedHolding = {
  ticker: 'ZZZ',
  symbol: 'ZZZ',
  exchange: null,
  name: null,
  value: 100,
};

function makePlan(
  unclassified: UnclassifiedHolding[],
  overrides: Partial<RebalancePlan> = {}
): RebalancePlan {
  const value = unclassified.reduce((sum, row) => sum + row.value, 0);
  return {
    policy: { targets: { equity: 100 }, tolerance_pct: 5 },
    total_value: 1000,
    classes: [],
    unclassified_value: value,
    unclassified_pct: value / 10,
    unclassified_holdings: unclassified,
    unpriced_tickers: [],
    accounts: [],
    trades: [],
    unfunded_amount: 0,
    notes: [],
    ...overrides,
  };
}

const renderPage = (path = '/strategy/classify?owner=alex') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <ClassifyHoldings />
    </MemoryRouter>
  );

describe('ClassifyHoldings page (#9495)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRoute.selectedOwner = '';
    mockSetInstrumentAssetClass.mockResolvedValue(undefined);
  });

  it("lists the owner's unclassified holdings", async () => {
    mockGetRebalancePlan.mockResolvedValue(makePlan([QQQ, BARE]));
    renderPage();
    expect(
      await screen.findByRole('link', { name: 'QQQ.N' })
    ).toBeInTheDocument();
    expect(mockGetRebalancePlan).toHaveBeenCalledWith('alex');
    expect(screen.getByText('Invesco QQQ')).toBeInTheDocument();
    expect(screen.getByLabelText('Asset class for QQQ.N')).toBeInTheDocument();
    // A ticker with no exchange cannot be addressed in the metadata store.
    expect(screen.getByText(/No exchange suffix/)).toBeInTheDocument();
    expect(
      screen.queryByLabelText('Asset class for ZZZ')
    ).not.toBeInTheDocument();
  });

  it('offers the canonical asset classes', async () => {
    mockGetRebalancePlan.mockResolvedValue(makePlan([QQQ]));
    renderPage();
    const select = await screen.findByLabelText('Asset class for QQQ.N');
    const values = within(select)
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value);
    expect(values).toEqual([
      '',
      'equity',
      'bond',
      'cash',
      'commodity',
      'property',
      'multi-asset',
    ]);
  });

  it('includes sleeve plans, summed by ticker', async () => {
    const sleeve = {
      id: 'growth',
      name: 'Growth',
      plan: makePlan([
        { ...QQQ, value: 50 },
        { ...BARE, ticker: 'YYY', symbol: 'YYY' },
      ]),
    } as RebalanceSleeveRow;
    mockGetRebalancePlan.mockResolvedValue(
      makePlan([QQQ], { sleeves: [sleeve] })
    );
    renderPage();
    expect(await screen.findByText('£300.00')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'YYY' })).toBeInTheDocument();
  });

  it('saves the chosen class and refetches the plan', async () => {
    mockGetRebalancePlan
      .mockResolvedValueOnce(makePlan([QQQ]))
      .mockResolvedValueOnce(makePlan([]));
    renderPage();
    const select = await screen.findByLabelText('Asset class for QQQ.N');
    const save = screen.getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled();
    fireEvent.change(select, { target: { value: 'equity' } });
    fireEvent.click(save);

    await waitFor(() =>
      expect(mockSetInstrumentAssetClass).toHaveBeenCalledWith(
        'QQQ',
        'N',
        'equity',
        'Invesco QQQ'
      )
    );
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Saved QQQ.N as Equity.'
    );
    expect(await screen.findByText(/nothing to classify/)).toBeInTheDocument();
    expect(mockGetRebalancePlan).toHaveBeenCalledTimes(2);
    expect(
      screen.queryByRole('link', { name: 'QQQ.N' })
    ).not.toBeInTheDocument();
  });

  it('shows the error and keeps the row when saving fails', async () => {
    mockGetRebalancePlan.mockResolvedValue(makePlan([QQQ]));
    mockSetInstrumentAssetClass.mockRejectedValue(new Error('boom'));
    renderPage();
    fireEvent.change(await screen.findByLabelText('Asset class for QQQ.N'), {
      target: { value: 'bond' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Could not save: boom')).toBeInTheDocument();
    expect(mockGetRebalancePlan).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: 'QQQ.N' })).toBeInTheDocument();
  });

  it('shows an empty state when nothing is unclassified', async () => {
    mockGetRebalancePlan.mockResolvedValue(makePlan([]));
    renderPage();
    expect(await screen.findByText(/nothing to classify/)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Back to Strategy' })
    ).toHaveAttribute('href', '/strategy');
  });

  it('falls back to the selected owner when the URL has none', async () => {
    mockRoute.selectedOwner = 'sam';
    mockGetRebalancePlan.mockResolvedValue(makePlan([]));
    renderPage('/strategy/classify');
    await screen.findByText(/nothing to classify/);
    expect(mockGetRebalancePlan).toHaveBeenCalledWith('sam');
  });

  it('asks for an owner when none is known', () => {
    renderPage('/strategy/classify');
    expect(
      screen.getByText(/Choose an owner on the Strategy page/)
    ).toBeInTheDocument();
    expect(mockGetRebalancePlan).not.toHaveBeenCalled();
  });
});
