import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest';

vi.mock('@/api', () => ({
  getTransactions: vi.fn(),
  updateTransaction: vi.fn(),
  splitTransaction: vi.fn(),
}));
vi.mock('@/hooks/useDemoReadOnly', () => ({
  useDemoReadOnly: () => ({ demoReadOnly: false, reason: () => undefined }),
}));

import { getTransactions, splitTransaction, updateTransaction } from '@/api';
import { InstrumentTransactions } from '@/components/InstrumentTransactions';

const ROW = {
  id: 'alice:ISA:0',
  owner: 'alice',
  account: 'isa',
  date: '2024-01-01',
  ticker: 'PFE',
  type: 'BUY',
  units: 10,
  price_gbp: 2,
  reason: 'diversify',
};

describe('InstrumentTransactions', () => {
  const mockGet = getTransactions as unknown as Mock;
  const mockSplit = splitTransaction as unknown as Mock;
  const mockUpdate = updateTransaction as unknown as Mock;

  beforeEach(() => {
    mockGet.mockReset().mockResolvedValue([ROW]);
    mockSplit
      .mockReset()
      .mockResolvedValue({ status: 'split', transactions: [] });
    mockUpdate.mockReset().mockResolvedValue(ROW);
  });

  it('lists transactions for the ticker', async () => {
    render(<InstrumentTransactions ticker="PFE" />);
    expect(await screen.findByText('alice')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith({ ticker: 'PFE' });
  });

  it('splits a transaction and reloads', async () => {
    const user = userEvent.setup();
    render(<InstrumentTransactions ticker="PFE" />);
    await user.click(await screen.findByRole('button', { name: 'Split' }));
    await user.type(screen.getByLabelText('Units in first part'), '4');
    await user.click(screen.getByRole('button', { name: 'Confirm split' }));
    await waitFor(() =>
      expect(mockSplit).toHaveBeenCalledWith('alice:ISA:0', 4)
    );
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
  });

  it("rejects a split size outside the transaction's units", async () => {
    const user = userEvent.setup();
    render(<InstrumentTransactions ticker="PFE" />);
    await user.click(await screen.findByRole('button', { name: 'Split' }));
    await user.type(screen.getByLabelText('Units in first part'), '10');
    await user.click(screen.getByRole('button', { name: 'Confirm split' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'between 0 and 10'
    );
    expect(mockSplit).not.toHaveBeenCalled();
  });

  it('edits a transaction via updateTransaction', async () => {
    const user = userEvent.setup();
    render(<InstrumentTransactions ticker="PFE" />);
    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    const units = screen.getByLabelText('Units');
    await user.clear(units);
    await user.type(units, '12');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(mockUpdate).toHaveBeenCalled());
    const [id, payload] = mockUpdate.mock.calls[0];
    expect(id).toBe('alice:ISA:0');
    expect(payload).toMatchObject({
      owner: 'alice',
      ticker: 'PFE',
      units: 12,
      price_gbp: 2,
    });
  });
});
