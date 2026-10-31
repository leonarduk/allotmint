import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Transaction } from '@/types';
import { TradeJournalPrompt } from '@/components/TradeJournalPrompt';

const api = vi.hoisted(() => ({
  getDecisionJournal: vi.fn(),
  createDecisionDraft: vi.fn(),
  confirmDecision: vi.fn(),
  dismissDecisionChange: vi.fn(),
  getInvestmentPlan: vi.fn(),
  saveDecisionLesson: vi.fn(),
  runDecisionJournal: vi.fn(),
}));

vi.mock('@/api', () => api);

// Synthetic owner, tickers and amounts only: rows as an import would persist them.
const row = (index: number, patch: Partial<Transaction>): Transaction => ({
  id: `alex:isa:${index}`,
  owner: 'alex',
  account: 'isa',
  date: '2026-10-01',
  type: 'BUY',
  ticker: 'AAA.L',
  units: 10,
  price_gbp: 100,
  ...patch,
});
const IMPORTED = [
  row(1, { type: 'SELL', ticker: 'AAA.L', units: 30 }),
  row(2, { units: 1 }),
  row(3, { type: 'DIVIDEND', units: null }),
  row(4, { ticker: 'BBB.L', units: 50 }),
];

describe('TradeJournalPrompt', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.getDecisionJournal.mockResolvedValue({
      settings: { threshold_gbp: 1000 },
      entries: [],
      unlogged: [],
    });
  });

  it('does not refetch the journal when re-rendered with the same rows', async () => {
    const { rerender } = render(
      <TradeJournalPrompt
        owner="alex"
        trades={[...IMPORTED]}
        onClose={vi.fn()}
      />
    );
    await screen.findByRole('region', { name: 'Log trade decisions' });
    rerender(
      <TradeJournalPrompt
        owner="alex"
        trades={[...IMPORTED]}
        onClose={vi.fn()}
      />
    );
    await screen.findByRole('region', { name: 'Log trade decisions' });
    expect(api.getDecisionJournal).toHaveBeenCalledTimes(1);
  });

  it('lists every qualifying imported row in one prompt', async () => {
    render(
      <TradeJournalPrompt owner="alex" trades={IMPORTED} onClose={vi.fn()} />
    );
    const prompt = await screen.findByRole('region', {
      name: 'Log trade decisions',
    });
    expect(
      within(prompt).getByText(/Trades of £1,000 or more/)
    ).toBeInTheDocument();
    expect(
      within(prompt).getByText('SELL £3,000 of AAA.L on 2026-10-01')
    ).toBeInTheDocument();
    expect(
      within(prompt).getByText('BUY £5,000 of BBB.L on 2026-10-01')
    ).toBeInTheDocument();
    expect(
      within(prompt).getAllByRole('button', { name: 'Log this decision?' })
    ).toHaveLength(2);
  });

  it('goes back to the remaining trades after one is logged, and closes after the last', async () => {
    const onClose = vi.fn();
    api.createDecisionDraft.mockImplementation(
      async (_owner, { source_ref }) => ({
        id: `dj-${source_ref}`,
        kind: 'trade',
        source_ref,
        date: '2026-10-01',
        decision: `Decision for ${source_ref}`,
        alternatives: [],
        reason: '',
        legs: [],
        snapshot: {},
      })
    );
    api.confirmDecision.mockResolvedValue({ id: 'dj' });
    render(
      <TradeJournalPrompt owner="alex" trades={IMPORTED} onClose={onClose} />
    );

    for (const ref of ['alex:isa:1', 'alex:isa:4']) {
      fireEvent.click(
        (
          await screen.findAllByRole('button', { name: 'Log this decision?' })
        )[0]
      );
      expect(api.createDecisionDraft).toHaveBeenLastCalledWith('alex', {
        source_ref: ref,
      });
      fireEvent.change(await screen.findByLabelText('Your reasoning'), {
        target: { value: 'My own reasons' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Log decision' }));
      await waitFor(() =>
        expect(api.confirmDecision).toHaveBeenLastCalledWith(
          'alex',
          expect.objectContaining({ source_ref: ref, reason: 'My own reasons' })
        )
      );
    }
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('renders nothing when no trade qualifies', async () => {
    const { container } = render(
      <TradeJournalPrompt
        owner="alex"
        trades={[row(2, { units: 1 })]}
        onClose={vi.fn()}
      />
    );
    await waitFor(() =>
      expect(api.getDecisionJournal).toHaveBeenCalledWith('alex')
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('reports a failed journal check and can still be dismissed', async () => {
    api.getDecisionJournal.mockRejectedValue(new Error('journal unavailable'));
    const onClose = vi.fn();
    render(
      <TradeJournalPrompt owner="alex" trades={IMPORTED} onClose={onClose} />
    );
    expect(
      await screen.findByText(
        'Could not check the decision journal: journal unavailable'
      )
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(onClose).toHaveBeenCalled();
    expect(api.dismissDecisionChange).not.toHaveBeenCalled();
  });
});
