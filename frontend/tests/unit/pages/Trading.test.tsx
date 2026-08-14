import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { axe } from 'jest-axe';
import Trading from '@/pages/Trading';
import useFetchWithRetry from '@/hooks/useFetchWithRetry';
import type { TradingAgentSettings, TradingSignal } from '@/types';

vi.mock('@/api', () => ({
  getTradingPageData: vi.fn(),
}));

vi.mock('@/hooks/useFetchWithRetry');

const mockUseFetchWithRetry = vi.mocked(useFetchWithRetry);

vi.mock('@/components/InstrumentDetail', () => ({
  InstrumentDetail: ({
    ticker,
    signal,
    onClose,
  }: {
    ticker: string;
    signal?: { action: string; reason: string };
    onClose: () => void;
  }) => (
    <div data-testid="detail">
      Detail for {ticker}
      {signal && (
        <div>
          {signal.action} - {signal.reason}
        </div>
      )}
      <button onClick={onClose}>x</button>
    </div>
  ),
}));

const sampleSignal: TradingSignal = {
  ticker: 'AAA',
  name: 'AAA',
  action: 'buy',
  reason: 'cheap',
  currency: 'USD',
  instrument_type: 'equity',
};

const defaultSettings: TradingAgentSettings = {
  rsi_buy: 30,
  rsi_sell: 70,
  rsi_window: 14,
  ma_short_window: 20,
  ma_long_window: 50,
  pe_max: null,
  de_max: null,
  min_sharpe: null,
  max_volatility: null,
};

function mockFetchState(overrides: {
  data?: TradingSignal[] | null;
  settings?: Partial<TradingAgentSettings>;
  loading?: boolean;
  error?: Error | null;
}) {
  mockUseFetchWithRetry.mockReturnValue({
    data:
      overrides.data === undefined
        ? null
        : {
            signals: overrides.data ?? [],
            settings: { ...defaultSettings, ...overrides.settings },
          },
    loading: overrides.loading ?? false,
    error: overrides.error ?? null,
    attempt: 0,
    maxAttempts: 5,
    unauthorized: false,
  });
}

describe('Trading page', () => {
  it('passes signal to InstrumentDetail', async () => {
    mockFetchState({ data: [sampleSignal] });

    render(<Trading />);

    const cell = await screen.findByText('AAA');
    fireEvent.click(cell);

    const detail = await screen.findByTestId('detail');
    expect(detail).toHaveTextContent(/buy/i);
    expect(detail).toHaveTextContent('cheap');
  });

  it('has no accessibility violations', async () => {
    mockFetchState({ data: [sampleSignal] });

    const { container } = render(<Trading />);
    await screen.findByText('AAA');
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('shows the empty state when the fetch succeeds with no signals', async () => {
    mockFetchState({ data: [] });

    render(<Trading />);

    expect(await screen.findByText('No signals right now')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Trading signals' })
    ).toBeInTheDocument();
    expect(screen.getByText('RSI buy below')).toBeInTheDocument();
    expect(
      screen.getByText(/No tracked instrument currently crosses/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/backend unavailable/i)).not.toBeInTheDocument();
  });

  it('renders "Not enabled" for null (disabled) thresholds', async () => {
    mockFetchState({
      data: [],
      settings: { rsi_buy: null, rsi_sell: null },
    });

    render(<Trading />);

    await screen.findByText('No signals right now');
    // rsi_buy, rsi_sell and the four optional filters are all disabled.
    expect(screen.getAllByText('Not enabled')).toHaveLength(6);
  });

  it('renders the signals table when signals exist', async () => {
    mockFetchState({ data: [sampleSignal] });

    render(<Trading />);

    expect(await screen.findByText('AAA')).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('Buy')).toBeInTheDocument();
    expect(screen.getByText('cheap')).toBeInTheDocument();
    expect(screen.queryByText('No signals right now')).not.toBeInTheDocument();
    expect(screen.getByText('1 active signals')).toBeInTheDocument();
  });

  it('shows a retryable backend-unavailable state on failure, distinct from the empty state', async () => {
    mockFetchState({ error: new Error('HTTP 503 - Service Unavailable') });

    render(<Trading />);

    const retryButton = await screen.findByRole('button', { name: /retry/i });
    expect(screen.getByText(/backend unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText('No signals right now')).not.toBeInTheDocument();

    fireEvent.click(retryButton);
    expect(mockUseFetchWithRetry).toHaveBeenLastCalledWith(
      expect.any(Function),
      500,
      5,
      1
    );
  });

  it('does not emit duplicate-key warnings when the same ticker appears twice (#6505)', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    mockFetchState({
      data: [
        { ticker: 'CASH', name: 'Cash GBP', action: 'buy', reason: 'a' },
        { ticker: 'CASH', name: 'Cash L', action: 'sell', reason: 'b' },
        { ticker: 'PFE', name: 'Pfizer N', action: 'buy', reason: 'c' },
        { ticker: 'PFE', name: 'Pfizer L', action: 'sell', reason: 'd' },
      ] as TradingSignal[],
    });

    render(<Trading />);

    expect(await screen.findAllByText('CASH')).toHaveLength(2);
    expect(screen.getAllByText('PFE')).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes('same key')
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });
});
