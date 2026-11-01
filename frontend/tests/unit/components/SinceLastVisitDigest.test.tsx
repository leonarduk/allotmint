import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import type { Account } from '@/types';

const mocks = vi.hoisted(() => ({
  getGroupMovers: vi.fn(),
  getAlerts: vi.fn(),
  getDividends: vi.fn(),
  recordLastVisit: vi.fn(),
  dismissLastVisit: vi.fn(),
}));

vi.mock('@/api', () => mocks);

import { SinceLastVisitDigest } from '@/components/SinceLastVisitDigest';
import { LAST_VISIT_KEY_PREFIX } from '@/lib/lastVisitStore';

const DAY = 24 * 60 * 60 * 1000;
const KEY = `${LAST_VISIT_KEY_PREFIX}family`;
const title = () => i18n.t('sinceLastVisit.title');
const NOT_STORED = { stored: false, previous: null, current: null };

const accounts: Account[] = [
  {
    owner: 'alice',
    account_type: 'isa',
    currency: 'GBP',
    value_estimate_gbp: 1000,
    holdings: [{ ticker: 'VOD.L', name: 'Vodafone' } as Account['holdings'][number]],
  },
];

const storeLocalVisit = (current: number) =>
  window.localStorage.setItem(KEY, JSON.stringify({ previous: null, current }));

describe('SinceLastVisitDigest', () => {
  beforeEach(() => {
    window.localStorage.clear();
    // No signed-in user by default: visits stay in this browser's localStorage.
    mocks.recordLastVisit.mockResolvedValue(NOT_STORED);
    mocks.dismissLastVisit.mockResolvedValue(NOT_STORED);
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

  describe('without a signed-in user (localStorage)', () => {
    it('renders nothing on a first visit and records it', async () => {
      const { container } = render(<SinceLastVisitDigest slug="family" accounts={accounts} />);
      await waitFor(() => expect(window.localStorage.getItem(KEY)).not.toBeNull());
      expect(container).toBeEmptyDOMElement();
      expect(JSON.parse(window.localStorage.getItem(KEY) ?? '{}').previous).toBeNull();
      expect(mocks.getGroupMovers).not.toHaveBeenCalled();
    });

    it('does not fetch until the portfolio has loaded', async () => {
      storeLocalVisit(Date.now() - 3 * DAY);
      render(<SinceLastVisitDigest slug="family" accounts={null} />);
      await waitFor(() => expect(mocks.recordLastVisit).toHaveBeenCalled());
      expect(mocks.getGroupMovers).not.toHaveBeenCalled();
    });

    it('summarises changes since the previous visit and can be dismissed', async () => {
      storeLocalVisit(Date.now() - 3 * DAY);
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
      storeLocalVisit(Date.now() - 3 * DAY);
      const first = render(<SinceLastVisitDigest slug="family" accounts={accounts} />);
      await screen.findByRole('region', { name: title() });

      const before = Date.now();
      await userEvent.click(screen.getByRole('button', { name: i18n.t('sinceLastVisit.dismiss') }));
      expect(mocks.dismissLastVisit).not.toHaveBeenCalled();
      const stored = JSON.parse(window.localStorage.getItem(KEY) ?? '{}');
      expect(stored.previous).toBeNull();
      expect(stored.current).toBeGreaterThanOrEqual(before);
      first.unmount();
      vi.clearAllMocks();
      mocks.recordLastVisit.mockResolvedValue(NOT_STORED);

      const { container } = render(<SinceLastVisitDigest slug="family" accounts={accounts} />);
      await waitFor(() => expect(mocks.recordLastVisit).toHaveBeenCalled());
      expect(container).toBeEmptyDOMElement();
      expect(mocks.getGroupMovers).not.toHaveBeenCalled();
    });

    it('shows no alerts when the group has no holdings loaded', async () => {
      storeLocalVisit(Date.now() - 3 * DAY);
      mocks.getGroupMovers.mockResolvedValue({ gainers: [], losers: [] });
      render(
        <SinceLastVisitDigest slug="family" accounts={[{ ...accounts[0], holdings: [] }]} />
      );

      const card = await screen.findByRole('region', { name: title() });
      expect(card).not.toHaveTextContent('VOD.L crossed your threshold');
      expect(card).toHaveTextContent(i18n.t('sinceLastVisit.nothingChanged', { days: 7 }));
    });

    it('explains an empty digest instead of rendering blank', async () => {
      storeLocalVisit(Date.now() - 3 * DAY);
      mocks.getGroupMovers.mockResolvedValue({ gainers: [], losers: [] });
      mocks.getAlerts.mockResolvedValue([]);
      render(<SinceLastVisitDigest slug="family" accounts={accounts} />);

      const card = await screen.findByRole('region', { name: title() });
      expect(card).toHaveTextContent(i18n.t('sinceLastVisit.nothingChanged', { days: 7 }));
    });

    it('labels movers with their own window rather than the visit date', async () => {
      const lastVisit = Date.now() - 2 * DAY;
      storeLocalVisit(lastVisit);
      render(<SinceLastVisitDigest slug="family" accounts={accounts} />);

      const card = await screen.findByRole('region', { name: title() });
      expect(mocks.getGroupMovers).toHaveBeenCalledWith('family', 7, 10);
      const moversLine = screen.getByText(/VOD\.L \+4\.50%/);
      expect(moversLine).toHaveTextContent('last 7 days');
      expect(moversLine).not.toHaveTextContent(new Date(lastVisit).toLocaleString());
      expect(moversLine).not.toHaveTextContent(/since/i);
      // The header names the visit without claiming every section starts there.
      expect(card).toHaveTextContent(
        i18n.t('sinceLastVisit.since', { date: new Date(lastVisit).toLocaleString() })
      );
      expect(card).not.toHaveTextContent(/changes since/i);
    });

    it('states the movers window when no holding moved much', async () => {
      storeLocalVisit(Date.now() - 3 * DAY);
      mocks.getGroupMovers.mockResolvedValue({ gainers: [], losers: [] });
      render(<SinceLastVisitDigest slug="family" accounts={accounts} />);

      await screen.findByRole('region', { name: title() });
      const line = screen.getByText(i18n.t('sinceLastVisit.noMovers', { days: 7 }));
      expect(line).toHaveTextContent('last 7 days');
    });

    it('says when a source failed rather than hiding it', async () => {
      storeLocalVisit(Date.now() - 3 * DAY);
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

  describe('with a signed-in user (server)', () => {
    const serverVisit = (previous: number | null) => ({
      stored: true,
      previous: previous === null ? null : new Date(previous).toISOString(),
      current: new Date().toISOString(),
    });

    it('compares against the visit the server returns and ignores localStorage', async () => {
      mocks.recordLastVisit.mockResolvedValue(serverVisit(Date.now() - 20 * DAY));
      render(<SinceLastVisitDigest slug="family" accounts={accounts} />);

      await screen.findByRole('region', { name: title() });
      expect(mocks.recordLastVisit).toHaveBeenCalledWith('family', undefined);
      // 20 days since the server's visit picks the 30-day movers window.
      expect(mocks.getGroupMovers).toHaveBeenCalledWith('family', 30, 10);
      expect(window.localStorage.getItem(KEY)).toBeNull();
    });

    it('seeds the server from the old localStorage record, then clears it', async () => {
      const old = Date.now() - 3 * DAY;
      storeLocalVisit(old);
      mocks.recordLastVisit.mockResolvedValue(serverVisit(old));
      render(<SinceLastVisitDigest slug="family" accounts={accounts} />);

      await screen.findByRole('region', { name: title() });
      expect(mocks.recordLastVisit).toHaveBeenCalledWith('family', {
        previous: null,
        current: new Date(old).toISOString(),
      });
      expect(window.localStorage.getItem(KEY)).toBeNull();
    });

    it('renders nothing on a first visit', async () => {
      mocks.recordLastVisit.mockResolvedValue(serverVisit(null));
      const { container } = render(<SinceLastVisitDigest slug="family" accounts={accounts} />);
      await waitFor(() => expect(mocks.recordLastVisit).toHaveBeenCalled());
      await Promise.resolve();
      expect(container).toBeEmptyDOMElement();
      expect(mocks.getGroupMovers).not.toHaveBeenCalled();
    });

    it('records a dismissal on the server, not in localStorage', async () => {
      mocks.recordLastVisit.mockResolvedValue(serverVisit(Date.now() - 3 * DAY));
      mocks.dismissLastVisit.mockResolvedValue(serverVisit(null));
      render(<SinceLastVisitDigest slug="family" accounts={accounts} />);
      await screen.findByRole('region', { name: title() });

      await userEvent.click(screen.getByRole('button', { name: i18n.t('sinceLastVisit.dismiss') }));
      expect(mocks.dismissLastVisit).toHaveBeenCalledWith('family');
      expect(screen.queryByRole('region', { name: title() })).not.toBeInTheDocument();
      expect(window.localStorage.getItem(KEY)).toBeNull();
    });

    it("falls back to this browser's record when the API is unavailable", async () => {
      storeLocalVisit(Date.now() - 3 * DAY);
      mocks.recordLastVisit.mockRejectedValue(new Error('503'));
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
      render(<SinceLastVisitDigest slug="family" accounts={accounts} />);

      await screen.findByRole('region', { name: title() });
      expect(mocks.getGroupMovers).toHaveBeenCalledWith('family', 7, 10);
      expect(JSON.parse(window.localStorage.getItem(KEY) ?? '{}').previous).not.toBeNull();
      expect(warn).toHaveBeenCalled();
      warn.mockRestore();
    });
  });
});
