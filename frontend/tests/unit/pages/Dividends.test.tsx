import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import Dividends from '@/pages/Dividends';
import {
  getDividends,
  getGroupPortfolio,
  getOwners,
  getPortfolio,
} from '@/api';

vi.mock('@/api', () => ({
  getDividends: vi.fn(),
  getGroupPortfolio: vi.fn(),
  getOwners: vi.fn(),
  getPortfolio: vi.fn(),
  getGbpRate: vi.fn(),
}));

const portfolio = (owner: string, tickers: [string, string][]) => ({
  owner,
  slug: 'all',
  as_of: '2026-10-07',
  accounts: [
    {
      account_type: 'isa',
      currency: 'GBP',
      value_estimate_gbp: 0,
      holdings: tickers.map(([ticker, name]) => ({ ticker, name, units: 1 })),
    },
  ],
});

describe('Dividends page', () => {
  const dividendsMock = getDividends as unknown as vi.Mock;
  const groupMock = getGroupPortfolio as unknown as vi.Mock;
  const portfolioMock = getPortfolio as unknown as vi.Mock;
  const ownersMock = getOwners as unknown as vi.Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    ownersMock.mockResolvedValue([
      { owner: 'alex', accounts: ['isa'] },
      { owner: 'joe', accounts: ['isa'] },
    ]);
    const recent = new Date();
    recent.setMonth(recent.getMonth() - 1);
    dividendsMock.mockResolvedValue([
      {
        owner: 'alex',
        account: 'isa',
        type: 'DIVIDEND',
        date: recent.toISOString().slice(0, 10),
        amount_minor: 1250,
        currency: 'GBP',
        ticker: 'PAY.L',
      },
      {
        owner: 'alex',
        account: 'isa',
        type: 'DIVIDEND',
        date: '2020-10-12',
        amount_minor: 500,
        currency: 'GBP',
      },
    ]);
    groupMock.mockResolvedValue(
      portfolio('all', [
        ['PAY.L', 'Payer plc'],
        ['NOPAY.L', 'Growth Fund'],
      ])
    );
    portfolioMock.mockResolvedValue(portfolio('joe', [['ONLY.L', 'Joe Fund']]));
  });

  it('shows trailing-12-month and all-time totals, and periods', async () => {
    render(<Dividends />);

    expect(
      await screen.findByTestId('dividends-trailing-12m')
    ).toHaveTextContent('£12.50');
    expect(screen.getByTestId('dividends-total')).toHaveTextContent('£17.50');
    expect(screen.getByRole('cell', { name: '2020/21' })).toBeInTheDocument();
  });

  it('marks held instruments with no dividend history instead of showing £0.00', async () => {
    render(<Dividends />);

    const row = (await screen.findByText('NOPAY.L')).closest(
      'tr'
    ) as HTMLElement;
    expect(
      within(row).getByText(i18n.t('dividends.noHistory'))
    ).toBeInTheDocument();
    expect(row).not.toHaveTextContent('£0.00');

    const unattributed = screen
      .getByText(i18n.t('dividends.unattributed'))
      .closest('tr') as HTMLElement;
    expect(unattributed).toHaveTextContent('£5.00');
  });

  it('refetches for the selected owner', async () => {
    render(<Dividends />);
    await screen.findByText('NOPAY.L');
    await screen.findByRole('option', { name: 'joe' });

    fireEvent.change(screen.getByLabelText(i18n.t('dividends.owner')), {
      target: { value: 'joe' },
    });

    await waitFor(() =>
      expect(dividendsMock).toHaveBeenLastCalledWith({ owner: 'joe' })
    );
    expect(portfolioMock).toHaveBeenCalledWith('joe');
    expect(await screen.findByText('ONLY.L')).toBeInTheDocument();
  });
});
