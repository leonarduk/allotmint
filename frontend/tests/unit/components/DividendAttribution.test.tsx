import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Transaction } from '@/types';
import DividendAttribution from '@/components/DividendAttribution';
import { unattributedDividends } from '@/lib/dividends';

const api = vi.hoisted(() => ({ attributeDividend: vi.fn() }));
vi.mock('@/api', () => api);

// Synthetic owner, tickers and amounts only (#10060).
const SWEEP: Transaction = {
  owner: 'alex',
  account: 'isa',
  id: 'alex:isa:1',
  type: 'DIVIDEND',
  date: '2026-06-10',
  amount_minor: 2185,
  comments: 'Transfer from Income Account',
};
const ROWS: Transaction[] = [
  SWEEP,
  { ...SWEEP, id: 'alex:isa:2', ticker: 'AAA.L', amount_minor: 500 },
  {
    ...SWEEP,
    id: 'alex:isa:3',
    ticker: null,
    estimated: true,
    amount_minor: 300,
  },
  { ...SWEEP, id: null },
  { ...SWEEP, id: 'alex:isa:4', type: 'DEPOSIT' },
  { ...SWEEP, id: 'alex:isa:5', attribution_only: true },
];

const openForm = () => {
  render(
    <DividendAttribution
      transactions={ROWS}
      tickers={['AAA.L', 'BBB.L']}
      onAttributed={onAttributed}
    />
  );
  fireEvent.click(screen.getByRole('button', { name: 'Split by holding' }));
};

const onAttributed = vi.fn();

describe('DividendAttribution', () => {
  beforeEach(() => {
    api.attributeDividend.mockReset();
    onAttributed.mockReset();
  });

  it('lists only booked dividends with no holding', () => {
    expect(unattributedDividends(ROWS).map((tx) => tx.id)).toEqual([
      'alex:isa:1',
    ]);
    render(
      <DividendAttribution
        transactions={[ROWS[1]]}
        tickers={[]}
        onAttributed={onAttributed}
      />
    );
    expect(screen.queryByTestId('dividend-attribution')).toBeNull();
  });

  it('splits a payment per holding in pence and leaves the rest unlinked', async () => {
    api.attributeDividend.mockResolvedValue({
      status: 'attributed',
      transactions: [],
    });
    openForm();
    fireEvent.change(screen.getByLabelText('Holding ticker'), {
      target: { value: 'aaa.l' },
    });
    fireEvent.change(screen.getByLabelText('Amount (£)'), {
      target: { value: '15.00' },
    });
    expect(screen.getByText('Left unlinked: £6.85')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save split' }));

    await waitFor(() => expect(onAttributed).toHaveBeenCalled());
    expect(api.attributeDividend).toHaveBeenCalledWith('alex:isa:1', [
      { ticker: 'AAA.L', amount_minor: 1500 },
    ]);
  });

  it('refuses parts that add up to more than the payment', () => {
    openForm();
    fireEvent.change(screen.getByLabelText('Holding ticker'), {
      target: { value: 'AAA.L' },
    });
    fireEvent.change(screen.getByLabelText('Amount (£)'), {
      target: { value: '21.86' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save split' }));

    expect(screen.getByRole('alert')).toHaveTextContent(
      'The parts add up to more than the payment.'
    );
    expect(api.attributeDividend).not.toHaveBeenCalled();
  });

  it('shows the server error and keeps the form open', async () => {
    api.attributeDividend.mockRejectedValue(new Error('Transaction not found'));
    openForm();
    fireEvent.change(screen.getByLabelText('Holding ticker'), {
      target: { value: 'AAA.L' },
    });
    fireEvent.change(screen.getByLabelText('Amount (£)'), {
      target: { value: '1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save split' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Transaction not found'
    );
    expect(onAttributed).not.toHaveBeenCalled();
  });
});
