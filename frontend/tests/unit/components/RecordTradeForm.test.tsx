import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest';

vi.mock('@/api', () => ({
  createTransaction: vi.fn(),
  getOwners: vi.fn(),
  getTransactions: vi.fn(),
  updateTransaction: vi.fn(),
  splitTransaction: vi.fn(),
}));
vi.mock('@/hooks/useDemoReadOnly', () => ({
  useDemoReadOnly: () => ({ demoReadOnly: false, reason: () => undefined }),
}));
vi.mock('@/hooks/useInstrumentHistory', () => ({
  invalidateInstrumentHistory: vi.fn(),
}));

import { createTransaction, getOwners, getTransactions } from '@/api';
import { invalidateInstrumentHistory } from '@/hooks/useInstrumentHistory';
import { RecordTradeForm } from '@/components/RecordTradeForm';
import { InstrumentTradeSection } from '@/components/InstrumentTradeSection';
import {
  buildTradeAccounts,
  defaultPriceUnit,
  toPriceGbp,
  tradeTotalGbp,
} from '@/components/transactions/recordTrade';
import type { InstrumentPosition } from '@/types';

const POSITIONS: InstrumentPosition[] = [
  { owner: 'steve', account: 'isa', units: 10 },
];
const OWNERS = [
  { owner: 'steve', accounts: ['isa', 'sipp'] },
  { owner: 'alice', accounts: ['isa'] },
];

const mockCreate = createTransaction as unknown as Mock;
const mockOwners = getOwners as unknown as Mock;
const mockGetTx = getTransactions as unknown as Mock;
const mockInvalidate = invalidateInstrumentHistory as unknown as Mock;

async function fillTrade(
  user: ReturnType<typeof userEvent.setup>,
  { units, price, fees }: { units: string; price: string; fees?: string }
) {
  await user.type(screen.getByLabelText('Units'), units);
  await user.type(screen.getByLabelText(/Price per unit/), price);
  if (fees) await user.type(screen.getByLabelText('Fees (£)'), fees);
  await user.type(screen.getByLabelText('Reason'), 'top up gold');
}

describe('recordTrade helpers', () => {
  it('defaults pence-quoted instruments to GBX', () => {
    expect(defaultPriceUnit('GBX')).toBe('GBX');
    expect(defaultPriceUnit('GBp')).toBe('GBX');
    expect(defaultPriceUnit('GBP')).toBe('GBP');
    expect(defaultPriceUnit(undefined)).toBe('GBP');
  });

  it('converts pence to pounds without float noise', () => {
    expect(toPriceGbp('28889.4', 'GBX')).toBe(288.894);
    expect(toPriceGbp('288.894', 'GBP')).toBe(288.894);
    expect(toPriceGbp('', 'GBX')).toBeNaN();
    expect(toPriceGbp('123.456', 'GBX')).toBe(1.23456);
    expect(toPriceGbp('0.1', 'GBX')).toBe(0.001);
    expect(toPriceGbp('12345.678901', 'GBX')).toBe(123.45678901);
  });

  it('adds fees to a buy and deducts them from a sell', () => {
    expect(tradeTotalGbp('BUY', 34, 288.894, 6.95)).toBeCloseTo(9829.346, 6);
    expect(tradeTotalGbp('SELL', 10, 2, 1)).toBe(19);
    expect(tradeTotalGbp('BUY', 0, 2, 1)).toBeNull();
  });

  it('lists holding accounts first, then the other owner accounts', () => {
    const accounts = buildTradeAccounts(POSITIONS, OWNERS);
    expect(accounts[0]).toEqual({ owner: 'steve', account: 'isa', heldUnits: 10 });
    expect(accounts).toHaveLength(3);
  });

  it('keeps /owners order when the instrument is not held anywhere', () => {
    const accounts = buildTradeAccounts([], OWNERS);
    expect(accounts.map((a) => `${a.owner}/${a.account}`)).toEqual([
      'steve/isa',
      'steve/sipp',
      'alice/isa',
    ]);
    expect(accounts.every((a) => a.heldUnits === 0)).toBe(true);
  });
});

describe('RecordTradeForm', () => {
  beforeEach(() => {
    mockCreate.mockReset().mockResolvedValue({ id: 'steve:isa:1' });
    mockOwners.mockReset().mockResolvedValue(OWNERS);
  });

  it('posts a BUY with the pence price converted to price_gbp', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(
      <RecordTradeForm
        ticker="PHGP.L"
        side="BUY"
        positions={POSITIONS}
        quoteCurrency="GBX"
        onSaved={onSaved}
        onCancel={vi.fn()}
      />
    );
    await fillTrade(user, { units: '34', price: '28889.4', fees: '6.95' });
    expect(screen.getByLabelText('Total')).toHaveTextContent('9,829.35');
    await user.click(screen.getByRole('button', { name: 'Record Buy' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    expect(mockCreate.mock.calls[0][0]).toMatchObject({
      owner: 'steve',
      account: 'isa',
      ticker: 'PHGP.L',
      type: 'BUY',
      units: 34,
      price_gbp: 288.894,
      fees: 6.95,
      reason: 'top up gold',
    });
    expect(mockCreate.mock.calls[0][0].date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(onSaved).toHaveBeenCalledWith('BUY');
  });

  it('sends the price unchanged when entered in pounds', async () => {
    const user = userEvent.setup();
    render(
      <RecordTradeForm
        ticker="PHGP.L"
        side="BUY"
        positions={POSITIONS}
        quoteCurrency="GBX"
        onSaved={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    await user.selectOptions(screen.getByLabelText('Price in'), 'GBP');
    await fillTrade(user, { units: '2', price: '288.89' });
    await user.click(screen.getByRole('button', { name: 'Record Buy' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    expect(mockCreate.mock.calls[0][0].price_gbp).toBe(288.89);
  });

  it('keeps save disabled until units and price are positive', async () => {
    const user = userEvent.setup();
    render(
      <RecordTradeForm
        ticker="PHGP.L"
        side="BUY"
        positions={POSITIONS}
        quoteCurrency="GBX"
        onSaved={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    const save = screen.getByRole('button', { name: 'Record Buy' });
    await fillTrade(user, { units: '0', price: '28889.4' });
    expect(save).toBeDisabled();
    await user.clear(screen.getByLabelText('Units'));
    await user.type(screen.getByLabelText('Units'), '34');
    await waitFor(() => expect(save).toBeEnabled());
  });

  it('warns and blocks a SELL above the units held until confirmed', async () => {
    const user = userEvent.setup();
    render(
      <RecordTradeForm
        ticker="PHGP.L"
        side="SELL"
        positions={POSITIONS}
        quoteCurrency="GBP"
        onSaved={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    await fillTrade(user, { units: '15', price: '290' });
    expect(
      screen.getByText(/Selling 15 units but this account holds 10/)
    ).toBeInTheDocument();
    const save = screen.getByRole('button', { name: 'Record Sell' });
    expect(save).toBeDisabled();
    await user.click(screen.getByLabelText('Record anyway'));
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    expect(mockCreate.mock.calls[0][0]).toMatchObject({ type: 'SELL', units: 15 });
  });

  it('does not warn for a SELL within the units held', async () => {
    const user = userEvent.setup();
    render(
      <RecordTradeForm
        ticker="PHGP.L"
        side="SELL"
        positions={POSITIONS}
        onSaved={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    await fillTrade(user, { units: '4', price: '290' });
    expect(screen.queryByText(/Selling/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Record Sell' })).toBeEnabled();
  });

  it('shows the API error and stays open when saving fails', async () => {
    const user = userEvent.setup();
    mockCreate.mockRejectedValueOnce(new Error('reason is required'));
    const onSaved = vi.fn();
    render(
      <RecordTradeForm
        ticker="PHGP.L"
        side="BUY"
        positions={POSITIONS}
        onSaved={onSaved}
        onCancel={vi.fn()}
      />
    );
    await fillTrade(user, { units: '1', price: '290' });
    await user.click(screen.getByRole('button', { name: 'Record Buy' }));
    expect(await screen.findByText('reason is required')).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });
});

describe('InstrumentTradeSection', () => {
  beforeEach(() => {
    mockCreate.mockReset().mockResolvedValue({ id: 'steve:isa:1' });
    mockOwners.mockReset().mockResolvedValue(OWNERS);
    mockGetTx.mockReset().mockResolvedValue([]);
    mockInvalidate.mockReset();
  });

  it('refreshes positions and transactions after a trade is saved', async () => {
    const user = userEvent.setup();
    render(
      <InstrumentTradeSection
        ticker="PHGP.L"
        positions={POSITIONS}
        quoteCurrency="GBX"
      />
    );
    await waitFor(() => expect(mockGetTx).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole('button', { name: 'Buy' }));
    await fillTrade(user, { units: '34', price: '28889.4', fees: '6.95' });
    await user.click(screen.getByRole('button', { name: 'Record Buy' }));
    await waitFor(() => expect(mockGetTx).toHaveBeenCalledTimes(2));
    expect(mockInvalidate).toHaveBeenCalledWith('PHGP.L');
    expect(
      screen.getByText('Buy of PHGP.L recorded.')
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('form', { name: /Record trade/ })
    ).not.toBeInTheDocument();
  });
});
