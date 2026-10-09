import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { BotDetail, BotRun, BotSummary } from '@/api';

const api = vi.hoisted(() => ({
  getBots: vi.fn(),
  getBot: vi.fn(),
  getBotRuns: vi.fn(),
  getBotRun: vi.fn(),
  runBotNow: vi.fn(),
  updateBotSettings: vi.fn(),
}));

vi.mock('@/api', () => api);

import Bots from '@/pages/Bots';

const lastRun: BotRun = {
  id: 'r1',
  bot_id: 'price-refresh',
  trigger: 'schedule',
  status: 'partial',
  started_at: '2026-10-09T00:00:00Z',
  duration_seconds: 12.5,
  summary: '98 of 100 tickers priced',
};

const bots: BotSummary[] = [
  {
    id: 'price-refresh',
    name: 'Price refresh',
    description: 'Fetches prices',
    kind: 'job',
    scope: 'system',
    enabled: true,
    cadence: 'daily',
    schedule: 'Daily at 00:00 UTC',
    next_run: '2026-10-10T00:00:00Z',
    running: false,
    last_run: lastRun,
  },
  {
    id: 'trading-agent',
    name: 'Trading agent signals',
    description: 'Signals',
    kind: 'rules',
    scope: 'system',
    enabled: false,
    cadence: 'daily',
    schedule: 'Daily at 01:00 UTC',
    next_run: null,
    running: false,
    last_run: null,
  },
];

function detail(overrides: Partial<BotDetail> = {}): BotDetail {
  return {
    ...bots[1],
    settings: { enabled: false, cadence: 'daily', rsi_buy: 30, rsi_window: 14 },
    settings_schema: {
      properties: {
        enabled: { type: 'boolean', title: 'Enabled' },
        cadence: {
          type: 'string',
          enum: ['daily', 'weekly', 'monthly'],
          title: 'Cadence',
        },
        rsi_buy: {
          anyOf: [{ type: 'number' }, { type: 'null' }],
          description: 'RSI at or below which to BUY',
        },
        rsi_window: { type: 'integer', description: 'RSI look-back (days)' },
      },
    },
    can_manage: true,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <Bots />
    </MemoryRouter>
  );
}

async function openTradingAgent() {
  renderPage();
  fireEvent.click(await screen.findByText('Trading agent signals'));
  return screen.findByRole('region', { name: 'Trading agent signals' });
}

describe('Bots page', () => {
  beforeEach(() => {
    api.getBots.mockResolvedValue(bots);
    api.getBot.mockResolvedValue(detail());
    api.getBotRuns.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('lists bots with last run status, summary and never-run state', async () => {
    renderPage();
    expect(await screen.findByText('Price refresh')).toBeInTheDocument();
    expect(screen.getByText('98 of 100 tickers priced')).toBeInTheDocument();
    const badges = screen
      .getAllByTestId('bot-status')
      .map((b) => b.textContent);
    expect(badges).toEqual(['Partial', 'Never run']);
    expect(screen.getByText('(disabled)')).toBeInTheDocument();
  });

  it('shows a load error', async () => {
    api.getBots.mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
  });

  it('renders a settings form from the JSON schema and saves it', async () => {
    api.updateBotSettings.mockResolvedValue(
      detail({ settings: { ...detail().settings, rsi_buy: 25 } })
    );
    const panel = await openTradingAgent();

    const rsi = within(panel).getByLabelText('RSI at or below which to BUY');
    fireEvent.change(rsi, { target: { value: '25' } });
    fireEvent.click(within(panel).getByRole('checkbox', { name: 'Enabled' }));
    fireEvent.click(
      within(panel).getByRole('button', { name: 'Save settings' })
    );

    await waitFor(() =>
      expect(api.updateBotSettings).toHaveBeenCalledWith(
        'trading-agent',
        expect.objectContaining({
          rsi_buy: 25,
          enabled: true,
          cadence: 'daily',
        })
      )
    );
    expect(
      await within(panel).findByText('Settings saved.')
    ).toBeInTheDocument();
  });

  it('clears a nullable number to null', async () => {
    api.updateBotSettings.mockResolvedValue(detail());
    const panel = await openTradingAgent();
    fireEvent.change(
      within(panel).getByLabelText('RSI at or below which to BUY'),
      {
        target: { value: '' },
      }
    );
    fireEvent.click(
      within(panel).getByRole('button', { name: 'Save settings' })
    );
    await waitFor(() =>
      expect(api.updateBotSettings).toHaveBeenCalledWith(
        'trading-agent',
        expect.objectContaining({ rsi_buy: null })
      )
    );
  });

  it('keeps unsaved edits when the panel re-fetches after a run', async () => {
    api.runBotNow.mockResolvedValue({
      ...lastRun,
      id: 'r4',
      bot_id: 'trading-agent',
      status: 'running',
    });
    const panel = await openTradingAgent();
    const rsi = within(panel).getByLabelText('RSI at or below which to BUY');
    fireEvent.change(rsi, { target: { value: '27' } });

    fireEvent.click(within(panel).getByRole('button', { name: 'Run now' }));
    await waitFor(() => expect(api.getBot).toHaveBeenCalledTimes(2));

    expect(
      within(panel).getByLabelText('RSI at or below which to BUY')
    ).toHaveValue(27);
  });

  it('shows validation errors from a 422', async () => {
    const err = Object.assign(new Error('HTTP 422'), {
      status: 422,
      body: {
        detail: [
          {
            loc: ['rsi_buy'],
            msg: 'Input should be less than or equal to 100',
          },
        ],
      },
    });
    api.updateBotSettings.mockRejectedValue(err);
    const panel = await openTradingAgent();
    fireEvent.click(
      within(panel).getByRole('button', { name: 'Save settings' })
    );
    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      'rsi_buy: Input should be less than or equal to 100'
    );
  });

  it('hides Run now and disables settings for non-admins', async () => {
    api.getBot.mockResolvedValue(detail({ can_manage: false }));
    const panel = await openTradingAgent();
    expect(within(panel).queryByRole('button', { name: 'Run now' })).toBeNull();
    expect(
      within(panel).queryByRole('button', { name: 'Save settings' })
    ).toBeNull();
    expect(
      within(panel).getByRole('checkbox', { name: 'Enabled' })
    ).toBeDisabled();
    expect(within(panel).getByText(/Only an admin/)).toBeInTheDocument();
  });

  it('starts a run and polls until it finishes', async () => {
    api.runBotNow.mockResolvedValue({
      ...lastRun,
      id: 'r2',
      bot_id: 'trading-agent',
      status: 'running',
    });
    api.getBotRun.mockResolvedValue({ ...lastRun, id: 'r2', status: 'ok' });
    const panel = await openTradingAgent();

    vi.useFakeTimers({ shouldAdvanceTime: true });
    fireEvent.click(within(panel).getByRole('button', { name: 'Run now' }));
    await waitFor(() =>
      expect(api.runBotNow).toHaveBeenCalledWith('trading-agent')
    );
    expect(
      await within(panel).findByRole('button', { name: 'Running…' })
    ).toBeDisabled();

    await vi.advanceTimersByTimeAsync(2100);
    await waitFor(() =>
      expect(api.getBotRun).toHaveBeenCalledWith('trading-agent', 'r2')
    );
    expect(
      await within(panel).findByRole('button', { name: 'Run now' })
    ).toBeEnabled();
  });

  it('shows the reason when a run is already in progress', async () => {
    api.runBotNow.mockRejectedValue(
      Object.assign(new Error('Bot trading-agent is already running'), {
        status: 409,
      })
    );
    const panel = await openTradingAgent();
    fireEvent.click(within(panel).getByRole('button', { name: 'Run now' }));
    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      'already running'
    );
  });

  it('shows run history with full errors and AI usage', async () => {
    api.getBotRuns.mockResolvedValue([
      {
        ...lastRun,
        id: 'r3',
        status: 'failed',
        summary: 'Failed: provider down',
        error:
          'Traceback (most recent call last):\nRuntimeError: provider down',
        model: 'claude-x',
        tokens_in: 1200,
        tokens_out: 300,
        cost_usd: 0.0123,
      },
    ]);
    const panel = await openTradingAgent();
    const run = await within(panel).findByTestId('bot-run');
    expect(run).toHaveTextContent('RuntimeError: provider down');
    expect(run).toHaveTextContent(
      'Model claude-x · 1200 in / 300 out tokens · $0.0123'
    );
  });
});
