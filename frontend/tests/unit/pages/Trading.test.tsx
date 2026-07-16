import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { axe } from 'jest-axe';
import Trading from '@/pages/Trading';
import useFetchWithRetry from '@/hooks/useFetchWithRetry';
import type { TradingSignal } from '@/types';

vi.mock('@/api', () => ({
  getTradingSignals: vi.fn(),
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

function mockFetchState(overrides: {
  data?: TradingSignal[] | null;
  loading?: boolean;
  error?: Error | null;
}) {
  mockUseFetchWithRetry.mockReturnValue({
    data: overrides.data ?? null,
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

    expect(await screen.findByText('No signals.')).toBeInTheDocument();
    expect(screen.queryByText(/backend unavailable/i)).not.toBeInTheDocument();
  });

  it('shows a retryable backend-unavailable state on failure, distinct from the empty state', async () => {
    mockFetchState({ error: new Error('HTTP 503 - Service Unavailable') });

    render(<Trading />);

    const retryButton = await screen.findByRole('button', { name: /retry/i });
    expect(screen.getByText(/backend unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText('No signals.')).not.toBeInTheDocument();

    fireEvent.click(retryButton);
    expect(mockUseFetchWithRetry).toHaveBeenLastCalledWith(
      expect.any(Function),
      500,
      5,
      1,
    );
  });
});
