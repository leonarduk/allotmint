import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import type { Account } from '@/types';

const mocks = vi.hoisted(() => ({
  getGroupMovers: vi.fn(),
  getAlerts: vi.fn(),
  getDividends: vi.fn(),
}));

vi.mock('@/api', () => mocks);

import {
  SinceLastVisitDigest,
  LAST_VISIT_KEY_PREFIX,
} from '@/components/SinceLastVisitDigest';

const DAY = 24 * 60 * 60 * 1000;
const KEY = `${LAST_VISIT_KEY_PREFIX}family`;
const title = () => i18n.t('sinceLastVisit.title');

const accounts: Account[] = [
  {
    owner: 'alice',
    account_type: 'isa',
    currency: 'GBP',
    value_estimate_gbp: 1000,
    holdings: [{ ticker: 'VOD.L', name: 'Vodafone' } as Account['holdings'][number]],
  },
];

describe('SinceLastVisitDigest', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mocks.getGroupMovers.mockResolvedValue({
      gainers: [{ ticker: 'VOD.L', name: 'Vodafone', change_pct: 4.5 }],
      losers: [],
    });
    mocks.getAlerts.mockResolvedValue([
      {
        ticker: 'VOD.L',
        change_pct: 4.5,
        message: 'VOD.L crossed your threshold',
        timestamp: new Date().toISOString(),
      },
    ]);
    mocks.getDividends.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing on a first visit and records it', () => {
    const { container } = render(<SinceLastVisitDigest slug="family" accounts={accounts} />);
    expect(container).toBeEmptyDOMElement();
    expect(JSON.parse(window.localStorage.getItem(KEY) ?? '{}').previous).toBeNull();
    expect(mocks.getGroupMovers).not.toHaveBeenCalled();
  });

  it('does not fetch until the portfolio has loaded', () => {
    window.localStorage.setItem(KEY, JSON.stringify({ previous: null, current: Date.now() - 3 * DAY }));
    render(<SinceLastVisitDigest slug="family" accounts={null} />);
    expect(mocks.getGroupMovers).not.toHaveBeenCalled();
  });

  it('summarises changes since the previous visit and can be dismissed', async () => {
    window.localStorage.setItem(KEY, JSON.stringify({ previous: null, current: Date.now() - 3 * DAY }));
    render(<SinceLastVisitDigest slug="family" accounts={accounts} />);

    const card = await screen.findByRole('region', { name: title() });
    expect(mocks.getGroupMovers).toHaveBeenCalledWith('family', 7, 10);
    expect(card).toHaveTextContent('VOD.L crossed your threshold');
    expect(card).toHaveTextContent('VOD.L +4.50%');
    expect(card).toHaveTextContent(i18n.t('sinceLastVisit.noDividends'));

    await userEvent.click(screen.getByRole('button', { name: i18n.t('sinceLastVisit.dismiss') }));
    expect(screen.queryByRole('region', { name: title() })).not.toBeInTheDocument();
  });

  it('treats dismissing as seen, so a reload does not bring the same delta back', async () => {
    window.localStorage.setItem(KEY, JSON.stringify({ previous: null, current: Date.now() - 3 * DAY }));
    const first = render(<SinceLastVisitDigest slug="family" accounts={accounts} />);
    await screen.findByRole('region', { name: title() });

    const before = Date.now();
    await userEvent.click(screen.getByRole('button', { name: i18n.t('sinceLastVisit.dismiss') }));
    const stored = JSON.parse(window.localStorage.getItem(KEY) ?? '{}');
    expect(stored.previous).toBeNull();
    expect(stored.current).toBeGreaterThanOrEqual(before);
    first.unmount();
    vi.clearAllMocks();

    const { container } = render(<SinceLastVisitDigest slug="family" accounts={accounts} />);
    expect(container).toBeEmptyDOMElement();
    expect(mocks.getGroupMovers).not.toHaveBeenCalled();
  });

  it('shows no alerts when the group has no holdings loaded', async () => {
    window.localStorage.setItem(KEY, JSON.stringify({ previous: null, current: Date.now() - 3 * DAY }));
    mocks.getGroupMovers.mockResolvedValue({ gainers: [], losers: [] });
    render(
      <SinceLastVisitDigest slug="family" accounts={[{ ...accounts[0], holdings: [] }]} />
    );

    const card = await screen.findByRole('region', { name: title() });
    expect(card).not.toHaveTextContent('VOD.L crossed your threshold');
    expect(card).toHaveTextContent(i18n.t('sinceLastVisit.nothingChanged'));
  });

  it('explains an empty digest instead of rendering blank', async () => {
    window.localStorage.setItem(KEY, JSON.stringify({ previous: null, current: Date.now() - 3 * DAY }));
    mocks.getGroupMovers.mockResolvedValue({ gainers: [], losers: [] });
    mocks.getAlerts.mockResolvedValue([]);
    render(<SinceLastVisitDigest slug="family" accounts={accounts} />);

    const card = await screen.findByRole('region', { name: title() });
    expect(card).toHaveTextContent(i18n.t('sinceLastVisit.nothingChanged'));
  });

  it('says when a source failed rather than hiding it', async () => {
    window.localStorage.setItem(KEY, JSON.stringify({ previous: null, current: Date.now() - 3 * DAY }));
    mocks.getGroupMovers.mockRejectedValue(new Error('down'));
    mocks.getAlerts.mockResolvedValue([]);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    render(<SinceLastVisitDigest slug="family" accounts={accounts} />);

    const card = await screen.findByRole('region', { name: title() });
    expect(card).toHaveTextContent(i18n.t('sinceLastVisit.moversUnavailable'));
    expect(card).toHaveTextContent(i18n.t('sinceLastVisit.noAlerts'));
    await waitFor(() => expect(warn).toHaveBeenCalled());
    warn.mockRestore();
  });
});
