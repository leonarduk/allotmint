import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  IndexBenchmarkRows,
  IndexRowsToggle,
} from '@/components/IndexBenchmarkRows';
import { useShowIndexRows } from '@/hooks/useShowIndexRows';
import type { IndexSummary } from '@/types';

const summary: IndexSummary = {
  indexes: [
    {
      name: 'FTSE 100',
      symbol: '^FTSE',
      currency: 'GBP',
      value: 8123.45,
      as_of: '2026-10-13T00:00:00',
      changes: {
        '1D': { change: -12.5, pct: -0.15, local_pct: -0.15 },
        '1W': { change: 40, pct: 0.5, local_pct: 0.5 },
        '1M': null,
        '1Y': { change: 600, pct: 7.98, local_pct: 7.98 },
      },
      total_return_1y: {
        pct: 11.5,
        symbol: 'ISF.L',
        source: 'etf',
        local_currency: 'GBP',
        local_pct: 11.5,
        fee_pct: 0.07,
      },
    },
    {
      name: 'FTSE 250',
      symbol: '^FTMC',
      currency: 'GBP',
      value: 20500,
      as_of: null,
      changes: { '1D': null, '1W': null, '1M': null, '1Y': null },
      total_return_1y: null,
    },
    {
      name: 'S&P 500',
      symbol: '^GSPC',
      currency: 'USD',
      value: 7700,
      as_of: null,
      changes: {
        '1D': null,
        '1W': { change: -40, pct: 0.4, local_pct: -0.5 },
        '1M': null,
        '1Y': null,
      },
      total_return_1y: {
        pct: 18.8,
        symbol: '^SP500TR',
        source: 'index',
        local_currency: 'USD',
        local_pct: 17.53,
        fee_pct: 0,
      },
    },
  ],
};

const mockGetIndexSummary = vi.fn(() => Promise.resolve(summary));

vi.mock('@/api', () => ({
  getIndexSummary: () => mockGetIndexSummary(),
}));

const renderRows = (relativeViewEnabled = false) =>
  render(
    <table>
      <tbody>
        <IndexBenchmarkRows relativeViewEnabled={relativeViewEnabled} />
      </tbody>
    </table>
  );

const cellTexts = (row: HTMLElement) =>
  within(row)
    .getAllByRole('cell')
    .map((cell) => cell.textContent);

describe('IndexBenchmarkRows', () => {
  beforeEach(() => {
    mockGetIndexSummary.mockClear();
    mockGetIndexSummary.mockImplementation(() => Promise.resolve(summary));
  });

  it('renders each index in points with money-only columns blank', async () => {
    renderRows();

    const row = await screen.findByTestId('index-row-^FTSE');
    expect(cellTexts(row)).toEqual([
      'FTSE 100',
      '8,123.45',
      '',
      '',
      '-12.50',
      '-0.15%',
      '+40.00 (0.50%)',
      '—',
      '+600.00 (7.98%)',
      '',
      '11.50%',
      '',
      '',
    ]);
  });

  it("matches the relative view's column count and shows only %", async () => {
    renderRows(true);

    const row = await screen.findByTestId('index-row-^FTSE');
    expect(cellTexts(row)).toEqual([
      'FTSE 100',
      '',
      '',
      '',
      '-0.15%',
      '0.50%',
      '—',
      '7.98%',
      '11.50%',
      '',
    ]);
  });

  it('names the total return source and shows — without one', async () => {
    renderRows();

    const ftse100 = await screen.findByTestId('index-row-^FTSE');
    expect(within(ftse100).getByText('11.50%')).toHaveAttribute(
      'title',
      'Proxy: ISF.L tracker ETF with dividends reinvested and its 0.07% annual fee added back'
    );
    const ftse250 = screen.getByTestId('index-row-^FTMC');
    expect(cellTexts(ftse250)[10]).toBe('—');
  });

  it('shows a converted total return in GBP with the USD figure in its tooltip', async () => {
    renderRows();

    const sp500 = await screen.findByTestId('index-row-^GSPC');
    const cellWithReturn = within(sp500).getByText('18.80%');
    expect(cellWithReturn).toHaveAttribute(
      'title',
      expect.stringContaining('17.53% in USD before conversion to GBP')
    );
    const ftse100 = screen.getByTestId('index-row-^FTSE');
    expect(within(ftse100).getByText('11.50%')).toHaveAttribute(
      'title',
      expect.not.stringContaining('before conversion')
    );
  });

  it('shows a US price change in GBP, coloured by it, with the USD move on hover', async () => {
    renderRows();

    const sp500 = await screen.findByTestId('index-row-^GSPC');
    const week = within(sp500).getByText('-40.00 (0.40%)');
    expect(week).toHaveAttribute(
      'title',
      '-0.50% in USD before conversion to GBP'
    );
    // Up in sterling though down in points: the colour follows the GBP %.
    expect(week).toHaveStyle({ color: 'var(--gain-positive)' });
    const ftse100 = screen.getByTestId('index-row-^FTSE');
    expect(within(ftse100).getByText('+40.00 (0.50%)')).not.toHaveAttribute(
      'title'
    );
  });

  it('collapses and expands the index rows from the Indices row', async () => {
    renderRows();
    await screen.findByTestId('index-row-^FTMC');

    fireEvent.click(screen.getByText('Indices'));
    expect(screen.queryByTestId('index-row-^FTMC')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Indices'));
    expect(screen.getByTestId('index-row-^FTMC')).toBeInTheDocument();
  });

  it('says when index data is unavailable', async () => {
    mockGetIndexSummary.mockImplementation(() =>
      Promise.reject(new Error('502'))
    );

    renderRows();

    expect(
      await screen.findByText('Index data is unavailable')
    ).toBeInTheDocument();
  });
});

function ToggleHarness() {
  const [show, setShow] = useShowIndexRows();
  return (
    <>
      <IndexRowsToggle checked={show} onChange={setShow} />
      <span data-testid="state">{String(show)}</span>
    </>
  );
}

describe('useShowIndexRows', () => {
  beforeEach(() => window.localStorage.clear());

  it('is off by default and remembers the choice', () => {
    const { unmount } = render(<ToggleHarness />);
    expect(screen.getByTestId('state')).toHaveTextContent('false');

    fireEvent.click(screen.getByLabelText('Show market indices'));
    expect(screen.getByTestId('state')).toHaveTextContent('true');
    unmount();

    render(<ToggleHarness />);
    expect(screen.getByTestId('state')).toHaveTextContent('true');
  });
});
