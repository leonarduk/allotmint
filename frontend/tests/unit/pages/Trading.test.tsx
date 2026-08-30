import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
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

    // The header's signal count must not claim a value while the backend
    // is unreachable -- `data` is null here (not "0 signals"), and showing
    // "0 active signals" next to "Backend unavailable" would tell a user
    // with live signals that there are none (#7229 regression).
    expect(screen.queryByText(/active signals/)).not.toBeInTheDocument();

    fireEvent.click(retryButton);
    expect(mockUseFetchWithRetry).toHaveBeenLastCalledWith(
      expect.any(Function),
      500,
      5,
      1
    );
  });

  it('shows page-shaped skeletons instead of a bare loading message while the fetch is pending (#7229)', async () => {
    mockFetchState({ loading: true });

    render(<Trading />);

    // The static header renders immediately -- it doesn't depend on the
    // slow /trading endpoint and shouldn't wait behind it.
    expect(
      screen.getByRole('heading', { name: 'Trading signals' })
    ).toBeInTheDocument();

    // The old bare "Loading…" paragraph that used to replace the whole page
    // is gone, replaced by qualified, screen-reader-announced skeletons.
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);

    // Exactly one live region per loading section (header count, settings,
    // signals) -- not one per skeleton placeholder. Regression guard for a
    // reviewed defect where 9 threshold rows x 2 skeletons each produced 18
    // simultaneous "polite" announcements of the same sentence.
    expect(screen.getAllByRole('status')).toHaveLength(3);

    // Threshold LABELS are static copy and render immediately; only the
    // values wait behind the fetch.
    expect(screen.getByText('RSI buy below')).toBeInTheDocument();
    expect(screen.getByText('Maximum volatility')).toBeInTheDocument();

    // Threshold values and real signal rows must not render prematurely --
    // only their skeleton placeholders.
    expect(screen.queryByText('Not enabled')).not.toBeInTheDocument();
    expect(screen.queryByText('No signals right now')).not.toBeInTheDocument();
  });

  it('attaches an InfoTip to jargon thresholds and the checks-skipped badge (#7230)', async () => {
    // 'compliance' and 'fundamental_screen' are the only two values the
    // backend ever emits (backend/agent/trading_agent.py:574-578) — see the
    // vocabulary-pinning test below.
    mockFetchState({
      data: [{ ...sampleSignal, checks_skipped: ['compliance', 'fundamental_screen'] }],
    });

    render(<Trading />);
    await screen.findByText('AAA');

    expect(
      screen.getAllByRole('button', { name: 'What does RSI mean?' }).length
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole('button', { name: "What does 'Checks skipped' mean?" })
    ).toBeInTheDocument();
  });

  it('pins the "Checks skipped" copy to the backend\'s actual checks_skipped vocabulary (#7230)', () => {
    // Guards against the copy drifting from what the backend can actually
    // emit — this is exactly how a previous review round caught the
    // explanation describing checks (P/E, Sharpe ratio, volatility) the
    // backend never tags as skipped, and omitting 'compliance' (the
    // consequential one) entirely. Checks both places that carry the same
    // claim (Trading.tsx's inline tooltip and MetricsExplanation.tsx's
    // glossary entry) since either can drift independently.
    const backendSource = readFileSync(
      resolve(__dirname, '../../../../backend/agent/trading_agent.py'),
      'utf-8'
    );
    const emitted = new Set(
      Array.from(
        backendSource.matchAll(/checks_skipped\.append\("([a-z_]+)"\)/g)
      ).map((match) => match[1])
    );
    expect(emitted).toEqual(new Set(['compliance', 'fundamental_screen']));

    const copySources = [
      resolve(__dirname, '../../../src/pages/Trading.tsx'),
      resolve(__dirname, '../../../src/pages/MetricsExplanation.tsx'),
    ].map((path) => readFileSync(path, 'utf-8'));

    for (const source of copySources) {
      for (const value of emitted) {
        expect(source).toContain(value);
      }
    }
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
