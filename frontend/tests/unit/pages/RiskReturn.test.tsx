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

  it('shows name and sector when hovering a legend entry', async () => {
    window.localStorage.setItem(
      'riskReturn.benchmarks',
      JSON.stringify([
        { ticker: '^FTSE', label: 'FTSE 100' },
        { ticker: 'FCIT.L', label: 'FCIT.L' },
      ])
    );
    benchmarkMock.mockImplementation((ticker: string, days: number) =>
      Promise.resolve({
        ticker,
        days,
        start: '',
        end: '',
        name: ticker === 'FCIT.L' ? 'F&C Investment Trust' : null,
        sector: ticker === 'FCIT.L' ? 'Global' : null,
        period_return: 0.08,
        annualised_return: null,
        volatility: 0.13,
      })
    );
    render(<RiskReturn />);

    const fcit = await screen.findByRole('checkbox', { name: 'FCIT.L' });
    await waitFor(() =>
      expect(fcit.closest('label')).toHaveAttribute(
        'title',
        'FCIT.L\nF&C Investment Trust\nGlobal'
      )
    );
    expect(
      screen.getByRole('checkbox', { name: 'FTSE 100' }).closest('label')
    ).toHaveAttribute(
      'title',
      'FTSE 100\nMarket index\nprice return, local currency'
    );
    expect(
      screen.getByRole('checkbox', { name: 'FCIT.L' }).closest('label')
    ).not.toHaveAttribute('title', expect.stringContaining('price return'));
  });

  it('starts the risk-free rate at the configured one and remembers an override', async () => {
    groupMock.mockResolvedValue({
      group: 'all',
      days: 365,
      start: '',
      end: '',
      missing_members: [],
      points: [],
      risk_free_rate: 0.04,
    });
    render(<RiskReturn />);

    const input = screen.getByLabelText(/Risk-free rate/);
    await waitFor(() => expect(input).toHaveValue(4));

    fireEvent.change(input, { target: { value: '3.5' } });

    expect(input).toHaveValue(3.5);
    expect(window.localStorage.getItem('riskReturn.riskFreePct')).toBe('3.5');
  });

  it('warns that short periods are noisy, but not from 3 years', async () => {
    render(<RiskReturn />);
    await screen.findByRole('checkbox', { name: 'Entire portfolio' });

    expect(screen.getByText(/shorter than 3 years/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Period'), {
      target: { value: String(365 * 3) },
    });

    await waitFor(() =>
      expect(screen.queryByText(/shorter than 3 years/)).not.toBeInTheDocument()
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

describe('RiskReturn average line', () => {
  it('is on by default and remembers being switched off', async () => {
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

    const toggle = await screen.findByRole('checkbox', {
      name: /Show average line/,
    });
    expect(toggle).toBeChecked();

    fireEvent.click(toggle);

    expect(toggle).not.toBeChecked();
    expect(window.localStorage.getItem('riskReturn.showAverage')).toBe('false');
  });
});

describe('RiskReturn average line rendering', () => {
  it('draws the line through the average of the plotted points, and removes it when switched off', async () => {
    window.localStorage.clear();
    (getGroups as unknown as vi.Mock).mockResolvedValue([]);
    (getOwners as unknown as vi.Mock).mockResolvedValue([]);
    groupMock.mockResolvedValue({
      group: 'all',
      days: 365,
      start: '',
      end: '',
      missing_members: [],
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
          period_return: 0.15,
          annualised_return: null,
          volatility: 0.2,
        },
      ],
    });
    benchmarkMock.mockReset();
    benchmarkMock.mockRejectedValue(new Error('down'));
    const { container } = render(<RiskReturn />);

    // No owner names are mocked here, so the label uses the slug.
    await screen.findByRole('checkbox', { name: 'steve ISA' });
    const averageLineEl = () =>
      container.querySelector(
        '.recharts-reference-line-line[stroke="var(--surface-muted-color)"]'
      );
    await waitFor(() => expect(averageLineEl()).not.toBeNull());

    fireEvent.click(
      screen.getByRole('checkbox', { name: /Show average line/ })
    );

    await waitFor(() => expect(averageLineEl()).toBeNull());
  });
});
