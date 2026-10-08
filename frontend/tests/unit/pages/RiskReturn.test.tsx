import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import RiskReturn from '@/pages/RiskReturn';
import {
  getBenchmarkRiskReturn,
  getGroupRiskReturn,
  getGroups,
  getOwners,
} from '@/api';

vi.mock('@/api', () => ({
  getBenchmarkRiskReturn: vi.fn(),
  getGroupRiskReturn: vi.fn(),
  getGroups: vi.fn(),
  getOwners: vi.fn(),
}));

const groupMock = getGroupRiskReturn as unknown as vi.Mock;
const benchmarkMock = getBenchmarkRiskReturn as unknown as vi.Mock;

describe('RiskReturn page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    (getGroups as unknown as vi.Mock).mockResolvedValue([
      { slug: 'all', name: 'All', members: ['steve', 'lucy'] },
    ]);
    (getOwners as unknown as vi.Mock).mockResolvedValue([
      { owner: 'steve', accounts: ['isa'], full_name: 'Steve' },
    ]);
    groupMock.mockResolvedValue({
      group: 'all',
      days: 365,
      start: '2025-10-07',
      end: '2026-10-07',
      missing_members: ['lucy'],
      points: [
        {
          kind: 'group',
          owner: null,
          account: null,
          period_return: 0.05,
          annualised_return: null,
          volatility: 0.1,
        },
        {
          kind: 'account',
          owner: 'steve',
          account: 'isa',
          period_return: 0.1,
          annualised_return: null,
          volatility: 0.2,
        },
      ],
    });
    benchmarkMock.mockImplementation((ticker: string, days: number) =>
      ticker === '^GSPC'
        ? Promise.reject(new Error('no data'))
        : Promise.resolve({
            ticker,
            days,
            start: '',
            end: '',
            period_return: 0.08,
            annualised_return: null,
            volatility: 0.13,
          })
    );
  });

  it('lists portfolio series and pre-populated index benchmarks', async () => {
    render(<RiskReturn />);

    expect(
      await screen.findByRole('checkbox', { name: 'Entire portfolio' })
    ).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Steve ISA' })).toBeChecked();
    expect(
      screen.getByText(/No transaction history for lucy/)
    ).toBeInTheDocument();
    expect(groupMock).toHaveBeenCalledWith('all', 365);
    for (const ticker of ['^FTSE', '^IXIC', '^GSPC']) {
      expect(benchmarkMock).toHaveBeenCalledWith(ticker, 365);
    }
    expect(
      screen.getByRole('checkbox', { name: /FTSE 100/ })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('checkbox', { name: /NASDAQ/ })
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole('checkbox', { name: /S&P 500.*no data/ })
      ).toBeInTheDocument()
    );
  });

  it('hides a series when unticked and remembers it', async () => {
    render(<RiskReturn />);

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Steve ISA' }));

    expect(
      screen.getByRole('checkbox', { name: 'Steve ISA' })
    ).not.toBeChecked();
    expect(
      JSON.parse(window.localStorage.getItem('riskReturn.hidden') ?? '[]')
    ).toEqual(['account:steve:isa']);
  });

  it('adds a typed ticker and removes a benchmark', async () => {
    render(<RiskReturn />);
    await screen.findByRole('checkbox', { name: 'Entire portfolio' });

    fireEvent.change(screen.getByLabelText('Add index or ticker'), {
      target: { value: 'vwrl.l' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() =>
      expect(benchmarkMock).toHaveBeenCalledWith('VWRL.L', 365)
    );
    expect(
      screen.getByRole('checkbox', { name: /^VWRL\.L/ })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove NASDAQ' }));
    expect(
      screen.queryByRole('checkbox', { name: /NASDAQ/ })
    ).not.toBeInTheDocument();
    expect(window.localStorage.getItem('riskReturn.benchmarks')).not.toContain(
      '^IXIC'
    );
  });

  it('rejects an invalid ticker', async () => {
    render(<RiskReturn />);
    await screen.findByRole('checkbox', { name: 'Entire portfolio' });

    fireEvent.change(screen.getByLabelText('Add index or ticker'), {
      target: { value: '../x' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Enter a ticker such as ^FTSE or VWRL.L.'
    );
  });

  it('refetches everything for a longer window', async () => {
    render(<RiskReturn />);
    await screen.findByRole('checkbox', { name: 'Entire portfolio' });

    fireEvent.change(screen.getByLabelText('Period'), {
      target: { value: String(365 * 3) },
    });

    await waitFor(() => expect(groupMock).toHaveBeenCalledWith('all', 365 * 3));
    await waitFor(() =>
      expect(benchmarkMock).toHaveBeenCalledWith('^FTSE', 365 * 3)
    );
    expect(screen.getAllByText('Annualised return').length).toBeGreaterThan(0);
  });
});

describe('RiskReturn benchmark retry', () => {
  it('refetches a failed benchmark when it is removed and re-added', async () => {
    window.localStorage.clear();
    (getGroups as unknown as vi.Mock).mockResolvedValue([]);
    (getOwners as unknown as vi.Mock).mockResolvedValue([]);
    groupMock.mockResolvedValue({
      group: 'all',
      days: 365,
      start: '',
      end: '',
      missing_members: [],
      points: [],
    });
    benchmarkMock.mockReset();
    benchmarkMock.mockRejectedValue(new Error('down'));
    render(<RiskReturn />);

    await screen.findByRole('checkbox', { name: /S&P 500.*no data/ });
    fireEvent.click(screen.getByRole('button', { name: 'Remove S&P 500' }));
    fireEvent.change(screen.getByLabelText('Add a common index…'), {
      target: { value: '^GSPC' },
    });

    await waitFor(() =>
      expect(
        benchmarkMock.mock.calls.filter(([t]) => t === '^GSPC')
      ).toHaveLength(2)
    );
  });
});
