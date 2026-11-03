import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BotSummary, BotsDigestSettings as Settings } from '@/api';

const mockGetSettings = vi.hoisted(() => vi.fn());
const mockUpdateSettings = vi.hoisted(() => vi.fn());
const mockGetBots = vi.hoisted(() => vi.fn());

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api');
  return {
    ...actual,
    getBotsDigestSettings: mockGetSettings,
    updateBotsDigestSettings: mockUpdateSettings,
    getBots: mockGetBots,
  };
});

import BotsDigestSettings from '@/components/BotsDigestSettings';

const DEFAULTS: Settings = {
  period: 'weekly',
  email_enabled: true,
  telegram_enabled: false,
  include_balances: false,
  send_when_empty: false,
  per_bot_cap: 5,
  alert_immediately_for: { 'trend-watch': ['high'] },
};

const BOTS = [
  { id: 'allowance-guardian', name: 'Allowance guardian' },
  { id: 'trend-watch', name: 'Trend watch' },
] as BotSummary[];

async function openPanel() {
  const user = userEvent.setup();
  render(<BotsDigestSettings owner="alex" />);
  await user.click(screen.getByText('Digest settings'));
  await screen.findByRole('form', { name: 'Digest settings' });
  return user;
}

describe('BotsDigestSettings', () => {
  beforeEach(() => {
    mockGetSettings.mockReset().mockResolvedValue(DEFAULTS);
    mockUpdateSettings.mockReset();
    mockGetBots.mockReset().mockResolvedValue(BOTS);
  });

  it('loads nothing until opened, then shows the saved settings', async () => {
    render(<BotsDigestSettings owner="alex" />);
    expect(mockGetSettings).not.toHaveBeenCalled();

    await userEvent.setup().click(screen.getByText('Digest settings'));

    await screen.findByRole('form', { name: 'Digest settings' });
    expect(mockGetSettings).toHaveBeenCalledWith('alex');
    expect(screen.getByRole('combobox')).toHaveValue('weekly');
    expect(
      screen.getByRole('checkbox', { name: 'Send the digest by email' })
    ).toBeChecked();
    expect(screen.getByRole('spinbutton')).toHaveValue(5);
    expect(
      screen.getByRole('checkbox', { name: 'Trend watch: High' })
    ).toBeChecked();
  });

  it('saves every field for the owner, dropping a bot with no severities', async () => {
    mockUpdateSettings.mockImplementation(async (_owner, values) => values);
    const user = await openPanel();

    await user.selectOptions(screen.getByRole('combobox'), 'monthly');
    await user.click(
      screen.getByRole('checkbox', {
        name: 'Show £ amounts in email and Telegram',
      })
    );
    await user.click(
      screen.getByRole('checkbox', {
        name: 'Send a digest even when nothing needs you',
      })
    );
    const cap = screen.getByRole('spinbutton');
    await user.clear(cap);
    await user.type(cap, '3');
    await user.click(
      screen.getByRole('checkbox', {
        name: 'Allowance guardian: Medium',
      })
    );
    await user.click(
      screen.getByRole('checkbox', {
        name: 'Allowance guardian: High',
      })
    );
    await user.click(
      screen.getByRole('checkbox', { name: 'Trend watch: High' })
    );
    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    await waitFor(() =>
      expect(mockUpdateSettings).toHaveBeenCalledWith('alex', {
        ...DEFAULTS,
        period: 'monthly',
        include_balances: true,
        send_when_empty: true,
        per_bot_cap: 3,
        alert_immediately_for: { 'allowance-guardian': ['high', 'medium'] },
      })
    );
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Settings saved.'
    );
  });

  it('shows the API validation errors', async () => {
    mockUpdateSettings.mockRejectedValue(
      Object.assign(new Error('422'), {
        body: {
          detail: [
            {
              loc: ['per_bot_cap'],
              msg: 'Input should be less than or equal to 50',
            },
          ],
        },
      })
    );
    const user = await openPanel();

    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'per_bot_cap: Input should be less than or equal to 50'
    );
  });

  it('reports a failed load', async () => {
    mockGetSettings.mockRejectedValue(new Error('boom'));
    render(<BotsDigestSettings owner="alex" />);

    await userEvent.setup().click(screen.getByText('Digest settings'));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the digest settings.'
    );
  });
});
