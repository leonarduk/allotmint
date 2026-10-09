import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DecisionDraft, DecisionJournalResponse } from '@/types';
import DecisionJournal from '@/components/DecisionJournal';

const api = vi.hoisted(() => ({
  getDecisionJournal: vi.fn(),
  getInvestmentPlan: vi.fn(),
  createDecisionDraft: vi.fn(),
  confirmDecision: vi.fn(),
  dismissDecisionChange: vi.fn(),
  saveDecisionLesson: vi.fn(),
  runDecisionJournal: vi.fn(),
}));

vi.mock('@/api', () => api);

// Synthetic owner, tickers and amounts only.
const journal: DecisionJournalResponse = {
  settings: { threshold_gbp: 1000 },
  unlogged: [
    {
      source_ref: 'alex:isa:7',
      date: '2026-10-01',
      type: 'SELL',
      ticker: 'AAA.L',
      amount_gbp: 10000,
    },
  ],
  entries: [
    {
      id: 'dj-old',
      date: '2026-01-02',
      kind: 'trade',
      legs: [],
      snapshot: {},
      review_due: ['2026-07-02', '2027-01-02'],
      reviews: [
        {
          horizon_months: 6,
          due: '2026-07-02',
          run_on: '2026-07-02',
          legs: [],
          comparisons: [],
          return_basis: 'total',
          expectation_outcome: 'met',
          summary: ['6-month review to 2026-07-02.'],
        },
      ],
    },
  ],
};

const draft: DecisionDraft = {
  id: 'dj-new',
  kind: 'trade',
  source_ref: 'alex:isa:7',
  date: '2026-10-01',
  decision: 'Sold £10,000 of AAA.L',
  alternatives: ['Keep holding AAA.L'],
  reason: '',
  amount_gbp: 10000,
  legs: [
    { role: 'chosen', label: 'Proceeds held as cash', ticker: null },
    { role: 'alternative', label: 'Keep holding AAA.L', ticker: 'AAA.L' },
  ],
  snapshot: { weights: { before_pct: 30, after_pct: 20 } },
};

const decisions = [
  {
    id: 'dj-old',
    date: '2026-01-02',
    decision: 'Sold BBB',
    alternatives: [],
  },
];

describe('DecisionJournal', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.getDecisionJournal.mockResolvedValue(journal);
    api.getInvestmentPlan.mockResolvedValue({ plan: { decisions } });
    api.createDecisionDraft.mockResolvedValue(draft);
    api.confirmDecision.mockResolvedValue({ id: 'dj-new' });
    api.dismissDecisionChange.mockResolvedValue({ dismissed: 'alex:isa:7' });
    api.saveDecisionLesson.mockResolvedValue({ lesson: 'x' });
    api.runDecisionJournal.mockResolvedValue({ unlogged: [], reviews_run: [] });
  });

  it('logs a qualifying SELL only after the owner writes the reasoning and confirms', async () => {
    const onLogged = vi.fn();
    render(<DecisionJournal owner="alex" onLogged={onLogged} />);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Log this decision?' })
    );
    expect(api.createDecisionDraft).toHaveBeenCalledWith('alex', {
      source_ref: 'alex:isa:7',
    });

    expect(await screen.findByLabelText('What was decided')).toHaveValue(
      'Sold £10,000 of AAA.L'
    );
    expect(screen.getByText(/weight 30% → 20%/)).toBeInTheDocument();
    const reason = screen.getByLabelText('Your reasoning');
    expect(reason).toHaveValue('');
    const confirm = screen.getByRole('button', { name: 'Log decision' });
    expect(confirm).toBeDisabled();
    expect(api.confirmDecision).not.toHaveBeenCalled();

    fireEvent.change(reason, { target: { value: 'My own reasons' } });
    fireEvent.change(screen.getByLabelText('What you expect to happen'), {
      target: { value: 'AAA keeps falling' },
    });
    fireEvent.click(confirm);

    await waitFor(() => expect(onLogged).toHaveBeenCalled());
    expect(api.confirmDecision).toHaveBeenCalledWith(
      'alex',
      expect.objectContaining({
        id: 'dj-new',
        reason: 'My own reasons',
        alternatives: ['Keep holding AAA.L'],
        expectation: { text: 'AAA keeps falling', check: undefined },
        legs: [
          { role: 'chosen', label: 'Proceeds held as cash', ticker: null },
          { role: 'alternative', label: 'Keep holding AAA.L', ticker: 'AAA.L' },
        ],
      })
    );
  });

  it('cancelling a draft writes nothing', async () => {
    render(<DecisionJournal owner="alex" />);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Log this decision?' })
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(api.confirmDecision).not.toHaveBeenCalled();
  });

  it('dismisses an unlogged change', async () => {
    render(<DecisionJournal owner="alex" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Not now' }));
    await waitFor(() =>
      expect(api.dismissDecisionChange).toHaveBeenCalledWith(
        'alex',
        'alex:isa:7'
      )
    );
  });

  it('shows logged decisions with their reviews and saves a lesson', async () => {
    render(<DecisionJournal owner="alex" />);
    expect(await screen.findByText('2026-01-02: Sold BBB')).toBeInTheDocument();
    expect(
      screen.getByText('6-month review to 2026-07-02.')
    ).toBeInTheDocument();
    expect(screen.getByText('Reviews due: 2027-01-02')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Lesson from the 6-month review'), {
      target: { value: 'Owner note' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }));
    await waitFor(() =>
      expect(api.saveDecisionLesson).toHaveBeenCalledWith(
        'alex',
        'dj-old',
        6,
        'Owner note'
      )
    );
  });

  it('offers to log a plan target change', async () => {
    const handled = vi.fn();
    render(
      <DecisionJournal
        owner="alex"
        planChange={{
          previous: { equity: 100 },
          current: { equity: 60, long_gilts: 40 },
        }}
        onPlanChangeHandled={handled}
      />
    );
    expect(
      screen.getByText('You changed the plan target. Log this decision?')
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getAllByRole('button', { name: 'Log this decision?' })[0]
    );
    await waitFor(() =>
      expect(api.createDecisionDraft).toHaveBeenCalledWith('alex', {
        previous_target: { equity: 100 },
        target: { equity: 60, long_gilts: 40 },
      })
    );
    expect(handled).toHaveBeenCalled();
  });
});
