import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TransactionsPage } from '@/components/TransactionsPage';

const {
  getTransactionsMock,
  createTransactionMock,
  getManualHoldingsMock,
  createManualHoldingMock,
} = vi.hoisted(() => ({
  getTransactionsMock: vi.fn(() =>
    Promise.resolve([
      {
        id: 'tx-1',
        owner: 'alex',
        account: 'isa',
        ticker: 'PFE',
        type: 'BUY',
        amount_minor: 10000,
        currency: 'GBP',
        shares: 5,
        date: '2024-01-01',
        reason: 'Initial',
      },
      {
        id: 'sam:sipp:1',
        owner: 'sam',
        account: 'sipp',
        ticker: 'MSFT',
        type: 'BUY',
        amount_minor: 20000,
        currency: 'GBP',
        units: 10,
        date: '2024-01-02',
        reason: 'Growth',
      },
    ])
  ),
  createTransactionMock: vi.fn(() => Promise.resolve({})),
  getManualHoldingsMock: vi.fn(() =>
    Promise.resolve({ owner: 'alex', accounts: [] })
  ),
  createManualHoldingMock: vi.fn(() => Promise.resolve({ status: 'saved' })),
}));

vi.mock('@/api', () => ({
  getTransactions: getTransactionsMock,
  createTransaction: createTransactionMock,
  getManualHoldings: getManualHoldingsMock,
  createManualHolding: createManualHoldingMock,
  updateTransaction: vi.fn(() => Promise.resolve({})),
  deleteTransaction: vi.fn(() => Promise.resolve({})),
}));

describe('TransactionsPage', () => {
  const getEditButtonForTicker = (ticker: string): HTMLButtonElement => {
    const tickerCell = screen.getByText(ticker);
    const row = tickerCell.closest('tr');
    if (!row) {
      throw new Error(`Could not find table row for ticker ${ticker}`);
    }
    return within(row).getByRole('button', { name: 'Edit' });
  };

  const getFilterOwner = () => screen.getAllByLabelText(/owner/i)[1];
  const getFilterAccount = () => screen.getAllByLabelText(/account/i)[1];
  const getEditorTicker = () => screen.getAllByLabelText('Ticker')[1];
  const getEditorPrice = () => screen.getAllByLabelText('Price (GBP)')[1];
  const getEditorUnits = () => screen.getAllByLabelText('Units')[1];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('displays instrument ticker', async () => {
    render(
      <TransactionsPage
        owners={[
          { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
          { owner: 'sam', full_name: 'Sam Example', accounts: ['sipp'] },
        ]}
      />
    );
    expect(await screen.findByText('PFE')).toBeInTheDocument();
    expect(
      (await screen.findAllByText('Alex Example')).at(-1)
    ).toBeInTheDocument();
  });

  it('locks owner and account filters while editing', async () => {
    render(
      <TransactionsPage
        owners={[
          { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
        ]}
      />
    );

    await screen.findByText('PFE');
    fireEvent.click(getEditButtonForTicker('PFE'));

    expect(getFilterOwner()).toBeDisabled();
    expect(getFilterAccount()).toBeDisabled();
    expect(
      screen.getByText(
        /owner and account filters are locked until you save or cancel/i
      )
    ).toBeInTheDocument();
  });

  it('rejects owner select interaction while editing (owner value stays unchanged)', async () => {
    const user = userEvent.setup();
    render(
      <TransactionsPage
        owners={[
          { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
          { owner: 'sam', full_name: 'Sam Example', accounts: ['sipp'] },
        ]}
      />
    );

    await screen.findByText('MSFT');
    const ownerFilter = getFilterOwner();
    const accountFilter = getFilterAccount();
    expect(ownerFilter).toHaveValue('');
    expect(accountFilter).toHaveValue('');

    await user.click(getEditButtonForTicker('PFE'));

    expect(ownerFilter).toHaveValue('alex');
    expect(accountFilter).toHaveValue('isa');
    expect(ownerFilter).toBeDisabled();
    expect(accountFilter).toBeDisabled();

    await user.selectOptions(ownerFilter, 'sam');
    expect(ownerFilter).toHaveValue('alex');
  });

  it('syncs filter owner/account when editing and reflects it in the editor context', async () => {
    render(
      <TransactionsPage
        owners={[
          { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
          { owner: 'sam', full_name: 'Sam Example', accounts: ['sipp'] },
        ]}
      />
    );

    await screen.findByText('MSFT');
    const ownerFilter = getFilterOwner();
    const accountFilter = getFilterAccount();

    expect(ownerFilter).toHaveValue('');
    expect(accountFilter).toHaveValue('');

    fireEvent.click(getEditButtonForTicker('MSFT'));

    expect(ownerFilter).toHaveValue('sam');
    expect(accountFilter).toHaveValue('sipp');
    expect(screen.getByText('sam / sipp')).toBeInTheDocument();
  });

  it('re-enables owner and account filters after canceling edit', async () => {
    const user = userEvent.setup();
    render(
      <TransactionsPage
        owners={[
          { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
          { owner: 'sam', full_name: 'Sam Example', accounts: ['sipp'] },
        ]}
      />
    );

    await screen.findByText('MSFT');
    const ownerFilter = getFilterOwner();
    const accountFilter = getFilterAccount();

    await user.click(getEditButtonForTicker('MSFT'));
    expect(ownerFilter).toBeDisabled();
    expect(accountFilter).toBeDisabled();
    expect(
      screen.getByText(
        /owner and account filters are locked until you save or cancel/i
      )
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(ownerFilter).not.toBeDisabled();
    expect(accountFilter).not.toBeDisabled();
    expect(
      screen.queryByText(
        /owner and account filters are locked until you save or cancel/i
      )
    ).not.toBeInTheDocument();
  });

  it('guards validation when submitting without filter owner/account context', async () => {
    render(
      <TransactionsPage
        owners={[
          { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
        ]}
      />
    );
    await screen.findByText('PFE');

    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '2024-03-01' },
    });
    fireEvent.change(getEditorTicker(), {
      target: { value: 'VUSA' },
    });
    fireEvent.change(getEditorPrice(), {
      target: { value: '10' },
    });
    fireEvent.change(getEditorUnits(), {
      target: { value: '2' },
    });
    fireEvent.change(screen.getByLabelText('Reason'), {
      target: { value: 'test reason' },
    });

    fireEvent.submit(
      screen.getByRole('button', { name: 'Add transaction' }).closest('form')!
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          'Select an owner and account in the filters before saving.'
        )
      ).toBeInTheDocument();
    });
    expect(createTransactionMock).not.toHaveBeenCalled();
  });

  it('uses the input-only variant without loading transactions', async () => {
    render(
      <TransactionsPage
        owners={[
          { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
        ]}
        inputOnly
      />
    );

    expect(
      await screen.findByText('Account + Holdings Input')
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Add transaction' })
    ).not.toBeInTheDocument();
    expect(getTransactionsMock).not.toHaveBeenCalled();
  });

  it('shows a targeted validation message when only one units field is provided', async () => {
    const user = userEvent.setup();
    render(
      <TransactionsPage
        owners={[
          { owner: 'alex', full_name: 'Alex Example', accounts: ['isa'] },
        ]}
        inputOnly
      />
    );

    await screen.findByText('Account + Holdings Input');
    await user.type(screen.getByLabelText('Account'), 'ISA');
    await user.type(screen.getByLabelText(/^Ticker$/i), 'VUSA.L');
    await user.type(screen.getByLabelText('Units'), '2');
    await user.click(screen.getByRole('button', { name: 'Save holding' }));

    expect(
      screen.getByText('Provide both Units and Price (GBP).')
    ).toBeInTheDocument();
    expect(createManualHoldingMock).not.toHaveBeenCalled();
  });
});
