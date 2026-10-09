import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BotsDigest as Digest, BotsDigestEntry } from '@/api';

const mockLatest = vi.hoisted(() => vi.fn());
const mockHistory = vi.hoisted(() => vi.fn());
const mockPreview = vi.hoisted(() => vi.fn());

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api');
  return {
    ...actual,
    getBotsDigestLatest: mockLatest,
    getBotsDigestHistory: mockHistory,
    getBotsDigestPreview: mockPreview,
  };
});

import BotsDigest from '@/components/BotsDigest';

function entry(over: Partial<BotsDigestEntry>): BotsDigestEntry {
  return {
    id: 'x',
    bot: 'cash-deployment',
    owner: 'alex',
    severity: 'medium',
    title: 'Tranche 3 due Monday',
    summary: '',
    link: null,
    action_required: false,
    created: '2026-10-12T07:00:00Z',
    dedupe_key: 'cash:t3',
    status: 'new',
    ...over,
  };
}

function digest(over: Partial<Digest> = {}): Digest {
  return {
    owner: 'alex',
    period: 'weekly',
    generated_at: '2026-10-12T07:00:00Z',
    opener: '2 items need you (1 new, 1 high severity).',
    items: [
      entry({
        severity: 'high',
        title: 'September contribution not received',
        dedupe_key: 'guardian:sept',
        action_required: true,
        status: 'still_open',
        link: '/bots',
      }),
      entry({ link: 'javascript:alert(1)' }),
    ],
    resolved: [
      entry({
        title: 'Decision logged',
        dedupe_key: 'journal:x',
        status: 'resolved',
      }),
    ],
    bots: [
      {
        bot: 'cash-deployment',
        name: 'Cash deployment',
        state: 'ok',
        last_run_at: null,
        summary: '',
      },
      {
        bot: 'trend-watch',
        name: 'Holding trend watch',
        state: 'not_run_yet',
        last_run_at: null,
        summary: '',
      },
    ],
    truncated: { 'cash-deployment': 2 },
    needs_owner: true,
    ...over,
  };
}

describe('BotsDigest (#10485)', () => {
  beforeEach(() => {
    mockLatest.mockReset();
    mockHistory.mockReset();
    mockPreview.mockReset();
    mockHistory.mockResolvedValue({ digests: [] });
  });

  it('renders ranked items with status, resolved items and bots not run yet', async () => {
    mockLatest.mockResolvedValue(digest());
    render(<BotsDigest owner="alex" />);

    const items = await screen.findAllByTestId('bots-digest-item');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('High');
    expect(items[0]).toHaveTextContent('September contribution not received');
    expect(items[0]).toHaveTextContent('Still open');
    expect(items[0]).toHaveTextContent('Action needed');
    expect(within(items[0]).getByRole('link')).toHaveAttribute('href', '/bots');
    // Unsafe links are not rendered as links.
    expect(within(items[1]).queryByRole('link')).toBeNull();
    expect(items[1]).toHaveTextContent('New');

    expect(screen.getByTestId('bots-digest-opener')).toHaveTextContent(
      '2 items need you'
    );
    expect(screen.getByTestId('bots-digest-resolved')).toHaveTextContent(
      'Decision logged'
    );
    expect(
      screen.getByText('Not run yet: Holding trend watch')
    ).toBeInTheDocument();
    expect(screen.getByText('2 more item(s) not shown.')).toBeInTheDocument();
    expect(mockLatest).toHaveBeenCalledWith('alex');
  });

  it('shows an empty state on 404 and can preview from the latest runs', async () => {
    mockLatest.mockRejectedValue(
      Object.assign(new Error('not found'), { status: 404 })
    );
    mockPreview.mockResolvedValue(
      digest({
        items: [],
        resolved: [],
        opener: 'Nothing needs you right now.',
      })
    );
    render(<BotsDigest owner="alex" />);

    expect(
      await screen.findByText('No digest has been composed yet.')
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Preview now' }));

    expect(
      await screen.findByText('Nothing needs you right now.')
    ).toBeInTheDocument();
    expect(screen.getByText(/Not saved or sent/)).toBeInTheDocument();
    expect(mockPreview).toHaveBeenCalledWith('alex');
  });

  it('shows an error for other failures', async () => {
    mockLatest.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 500 })
    );
    render(<BotsDigest owner="alex" />);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the digest.'
    );
  });

  it('lists history and opens an older digest', async () => {
    mockLatest.mockResolvedValue(digest());
    const older = digest({
      generated_at: '2026-10-05T07:00:00Z',
      items: [],
      resolved: [],
      opener: 'Nothing needs you right now.',
    });
    mockHistory.mockResolvedValue({ digests: [digest(), older] });
    render(<BotsDigest owner="alex" />);

    const history = await screen.findByTestId('bots-digest-history');
    await userEvent.click(
      within(history).getByRole('button', { name: '2026-10-05: 0 item(s)' })
    );
    expect(screen.getByTestId('bots-digest-opener')).toHaveTextContent(
      'Nothing needs you right now.'
    );
  });
});
