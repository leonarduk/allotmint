import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  recordLastVisit: vi.fn(),
  dismissLastVisit: vi.fn(),
}));

vi.mock('@/api', () => mocks);

import { LAST_VISIT_KEY_PREFIX, recordDismissal, recordVisit } from '@/lib/lastVisitStore';

const KEY = `${LAST_VISIT_KEY_PREFIX}family`;
const NOW = Date.UTC(2026, 9, 1, 9, 0, 0);
const DAY = 24 * 60 * 60 * 1000;
const local = () => JSON.parse(window.localStorage.getItem(KEY) ?? 'null');

describe('lastVisitStore', () => {
  let warn: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    window.localStorage.clear();
    warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    warn.mockRestore();
    vi.clearAllMocks();
  });

  it('returns the server previous visit as epoch ms', async () => {
    mocks.recordLastVisit.mockResolvedValue({
      stored: true,
      previous: '2026-09-28T09:00:00+00:00',
      current: '2026-10-01T09:00:00+00:00',
    });
    await expect(recordVisit('family', NOW)).resolves.toEqual({
      since: NOW - 3 * DAY,
      source: 'server',
    });
  });

  it('does not send a malformed local record as a seed', async () => {
    window.localStorage.setItem(KEY, JSON.stringify({ current: 'yesterday' }));
    mocks.recordLastVisit.mockResolvedValue({ stored: true, previous: null, current: 'x' });
    await recordVisit('family', NOW);
    expect(mocks.recordLastVisit).toHaveBeenCalledWith('family', undefined);
    expect(local()).toBeNull();
  });

  it('keeps the visit locally when the server does not store it', async () => {
    window.localStorage.setItem(KEY, JSON.stringify({ previous: null, current: NOW - DAY }));
    mocks.recordLastVisit.mockResolvedValue({ stored: false, previous: null, current: null });
    await expect(recordVisit('family', NOW)).resolves.toEqual({ since: NOW - DAY, source: 'local' });
    expect(local()).toEqual({ previous: NOW - DAY, current: NOW });
    expect(warn).not.toHaveBeenCalled();
  });

  it('falls back to localStorage when the server call fails', async () => {
    mocks.recordLastVisit.mockRejectedValue(new Error('down'));
    await expect(recordVisit('family', NOW)).resolves.toEqual({ since: null, source: 'local' });
    expect(local()).toEqual({ previous: null, current: NOW });
    expect(warn).toHaveBeenCalled();
  });

  it('dismisses locally without calling the server for a local visit', async () => {
    await recordDismissal('family', NOW, 'local');
    expect(mocks.dismissLastVisit).not.toHaveBeenCalled();
    expect(local()).toEqual({ previous: null, current: NOW });
  });

  it('dismisses on the server, falling back to localStorage when that fails', async () => {
    mocks.dismissLastVisit.mockResolvedValue({ stored: true, previous: null, current: 'x' });
    await recordDismissal('family', NOW, 'server');
    expect(local()).toBeNull();

    mocks.dismissLastVisit.mockRejectedValue(new Error('down'));
    await recordDismissal('family', NOW, 'server');
    expect(local()).toEqual({ previous: null, current: NOW });
    expect(warn).toHaveBeenCalled();
  });
});
