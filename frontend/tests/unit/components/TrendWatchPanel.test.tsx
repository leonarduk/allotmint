import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TrendWatchPanel from '@/components/TrendWatchPanel';
import type { TrendWatchItem, TrendWatchReport } from '@/types';

const api = vi.hoisted(() => ({
  getOwners: vi.fn(),
  getTrendWatchLatest: vi.fn(),
  runTrendWatch: vi.fn(),
  setTrendWatchMute: vi.fn(),
}));

vi.mock('@/api', () => api);

function item(overrides: Partial<TrendWatchItem>): TrendWatchItem {
  return {
    rank: 1,
    ticker: 'TURN.L',
    name: 'Turn plc',
    instrument_type: 'Equity',
    muted: false,
    change_score: 1.2,
    verdict: 'idiosyncratic_deterioration',
    verdict_label: 'Idiosyncratic deterioration',
    detection: {
      as_of: '2025-03-07',
      active: ['death_cross', 'below_falling_sma200', 'rs_new_low'],
      new: ['death_cross'],
      values: {},
    },
    context: {
      market_value_gbp: 15000,
      portfolio_share: 0.15,
      cost_basis_gbp: 16000,
      gain_pct: -0.0625,
      cgt_note:
        'Held only in ISA/SIPP wrappers: no capital gains tax on a disposal.',
    },
    investigation: {
      status: 'ok',
      summary: 'A profit warning on 2 March.',
      evidence: [
        {
          tool: 'search_web',
          finding: 'Profit warning',
          value: '-30% vs consensus',
          return_basis: 'not stated',
          source: 'https://example.com/rns',
        },
      ],
      tool_calls: [
        {
          tool: 'search_web',
          arguments: { query: 'Turn plc' },
          is_error: false,
          result: 'RNS: profit warning',
        },
      ],
      notes: [],
    },
    ...overrides,
  };
}

const REPORT: TrendWatchReport = {
  owner: 'alex',
  run_date: '2025-03-08',
  generated_at: '2025-03-08T06:00:00Z',
  disclaimer: 'A review list, not trade instructions.',
  holdings_checked: 12,
  items: [
    item({}),
    item({
      rank: 2,
      ticker: 'BETA.L',
      name: 'Beta plc',
      verdict: 'market_wide_move',
      verdict_label: 'Market-wide move',
    }),
    item({
      rank: 3,
      ticker: 'JEGI.L',
      name: 'JEGI',
      verdict: 'data_problem',
      verdict_label: 'Data problem, check first',
      data_issues: [
        {
          id: 'x',
          type: 'PRICE_SCALE_SUSPECT',
          severity: 'high',
          description: 'Close moved from 120 to 1.2',
          suggested_fix: 'Check the series.',
        },
      ],
    }),
  ],
  skipped: [],
  mutes: [],
  backtest: {
    tickers_tested: 10,
    excluded: {},
    return_basis: { total: 9, price: 1 },
    horizons: {
      '1m': {
        days: 21,
        flags: 40,
        flag_falls: 16,
        flag_fall_rate: 0.4,
        weeks: 900,
        base_falls: 405,
        base_rate: 0.45,
      },
      '3m': {
        days: 63,
        flags: 38,
        flag_falls: 15,
        flag_fall_rate: 0.39,
        weeks: 850,
        base_falls: 357,
        base_rate: 0.42,
      },
    },
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getOwners.mockResolvedValue([{ owner: 'alex', accounts: [] }]);
  api.getTrendWatchLatest.mockResolvedValue(REPORT);
});

describe('TrendWatchPanel', () => {
  it('renders the ranked list with verdict badges and the disclaimer', async () => {
    render(<TrendWatchPanel owner="alex" />);

    expect(await screen.findByTestId('trend-item-TURN.L')).toBeInTheDocument();
    expect(api.getTrendWatchLatest).toHaveBeenCalledWith('alex');
    expect(screen.getByText('Idiosyncratic deterioration')).toBeInTheDocument();
    expect(screen.getByText('Market-wide move')).toBeInTheDocument();
    expect(screen.getByText('Data problem, check first')).toBeInTheDocument();
    expect(
      screen.getByText('A review list, not trade instructions.')
    ).toBeInTheDocument();
    expect(screen.queryByText(/\b(sell|buy)\b/i)).not.toBeInTheDocument();
  });

  it('shows the evidence and tool calls behind a verdict', async () => {
    render(<TrendWatchPanel owner="alex" />);
    const card = await screen.findByTestId('trend-item-TURN.L');

    fireEvent.click(within(card).getByText('Evidence'));

    expect(
      within(card).getByText('A profit warning on 2 March.')
    ).toBeInTheDocument();
    expect(within(card).getByRole('link', { name: 'source' })).toHaveAttribute(
      'href',
      'https://example.com/rns'
    );
    expect(
      within(card).getByText(/search_web\(\{"query":"Turn plc"\}\)/)
    ).toBeInTheDocument();
    expect(
      within(card).getByText(/return basis: not stated/)
    ).toBeInTheDocument();
    const jegi = screen.getByTestId('trend-item-JEGI.L');
    expect(within(jegi).getByText('PRICE_SCALE_SUSPECT')).toBeInTheDocument();
  });

  it("shows the detector's hit rate and warns when it is no better than the base rate", async () => {
    render(<TrendWatchPanel owner="alex" />);

    expect(
      await screen.findByText('Track record of this detector')
    ).toBeInTheDocument();
    expect(screen.getByText('40%')).toBeInTheDocument();
    expect(screen.getByText('45%')).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent(
      /Over 1m, 3m, a flag on these holdings has been no better than the base rate/
    );
  });

  it('mutes and unmutes a holding', async () => {
    api.setTrendWatchMute
      .mockResolvedValueOnce({ mutes: ['TURN.L'] })
      .mockResolvedValueOnce({ mutes: [] });
    render(<TrendWatchPanel owner="alex" />);
    const card = await screen.findByTestId('trend-item-TURN.L');

    fireEvent.click(
      within(card).getByRole('button', { name: 'Mute (long-term holding)' })
    );
    await waitFor(() =>
      expect(
        within(card).getByRole('button', { name: 'Unmute' })
      ).toBeInTheDocument()
    );
    expect(api.setTrendWatchMute).toHaveBeenCalledWith('alex', 'TURN.L', true);
    expect(within(card).getByText('Long-term holding')).toBeInTheDocument();

    fireEvent.click(within(card).getByRole('button', { name: 'Unmute' }));
    await waitFor(() =>
      expect(
        within(card).getByRole('button', { name: 'Mute (long-term holding)' })
      ).toBeInTheDocument()
    );
    expect(api.setTrendWatchMute).toHaveBeenLastCalledWith(
      'alex',
      'TURN.L',
      false
    );
  });

  it('reflects a mute when the server returns the ticker upper-cased', async () => {
    api.getTrendWatchLatest.mockResolvedValue({
      ...REPORT,
      items: [item({ ticker: 'turn.l' })],
    });
    api.setTrendWatchMute.mockResolvedValue({ mutes: ['TURN.L'] });
    render(<TrendWatchPanel owner="alex" />);
    const card = await screen.findByTestId('trend-item-turn.l');

    fireEvent.click(
      within(card).getByRole('button', { name: 'Mute (long-term holding)' })
    );

    await waitFor(() =>
      expect(
        within(card).getByRole('button', { name: 'Unmute' })
      ).toBeInTheDocument()
    );
  });

  it('offers a run when there is no report yet, and shows the new report', async () => {
    api.getTrendWatchLatest.mockResolvedValue(null);
    api.runTrendWatch.mockResolvedValue({ ...REPORT, items: [] });
    render(<TrendWatchPanel owner="alex" />);

    expect(
      await screen.findByText(/No trend-watch report yet/)
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Run now' }));

    expect(
      await screen.findByText(/No holding has newly turned down/)
    ).toBeInTheDocument();
    expect(api.runTrendWatch).toHaveBeenCalledWith('alex');
  });

  it('reports a failed run', async () => {
    api.runTrendWatch.mockRejectedValue(new Error('boom'));
    render(<TrendWatchPanel owner="alex" />);
    await screen.findByTestId('trend-item-TURN.L');

    fireEvent.click(screen.getByRole('button', { name: 'Run now' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
  });

  it('falls back to the first owner when none is selected', async () => {
    render(<TrendWatchPanel />);

    await waitFor(() =>
      expect(api.getTrendWatchLatest).toHaveBeenCalledWith('alex')
    );
  });
});
