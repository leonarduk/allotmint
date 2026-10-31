import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { DecisionPatterns as Patterns } from '@/types';
import DecisionPatterns from '@/components/DecisionPatterns';
import en from '@/locales/en/translation.json';

// Synthetic counts only.
const patterns: Patterns = {
  min_reviewed: 5,
  reviewed_entries: 11,
  groups: [
    {
      kind: 'trade',
      trade_type: 'SELL',
      trend_watch: 'flagged',
      horizon_months: 6,
      split_by_basis: true,
      rows: [
        {
          alternative: 'same_instrument',
          return_basis: 'total',
          comparisons: 6,
          above: 4,
          below: 1,
          level: 1,
          first_date: '2026-01-05',
          last_date: '2026-02-09',
        },
        {
          alternative: 'same_instrument',
          return_basis: 'mixed',
          comparisons: 5,
          above: 0,
          below: 5,
          level: 0,
          first_date: '2026-03-02',
          last_date: '2026-03-30',
        },
      ],
    },
  ],
};

// Advisory or judging language the pattern text must never use (as in tests/backend/decision_journal/test_review.py).
const ADVISORY =
  /\b(right|wrong|should|mistake|good|bad|better|worse|recommend\w*|advi[cs]e\w*|regret\w*|wise|unwise|smart|correct|incorrect|buy now|sell now|switch)\b/i;

describe('DecisionPatterns', () => {
  it('states the counts per group, row and return basis', () => {
    render(<DecisionPatterns patterns={patterns} />);
    expect(
      screen.getByText(
        'Sells · 6-month reviews · on the trend-watch list when logged'
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Against the instrument traded (total return): the option taken ended above in 4, below in 1 and level in 1 of 6 comparisons; decisions dated 2026-01-05 to 2026-02-09.'
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(/mixed bases: total return against price return/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Counts are split by return basis/)
    ).toBeInTheDocument();
  });

  it('shows no pattern text below the minimum', () => {
    render(
      <DecisionPatterns
        patterns={{ min_reviewed: 5, reviewed_entries: 3, groups: [] }}
      />
    );
    expect(
      screen.getByText(
        'No count has 5 or more comparisons behind it yet. Decisions reviewed so far: 3.'
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/ended above/)).not.toBeInTheDocument();
  });

  it('renders nothing before any decision is reviewed', () => {
    const { container } = render(
      <DecisionPatterns
        patterns={{ min_reviewed: 5, reviewed_entries: 0, groups: [] }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('uses factual wording only', () => {
    const text = Object.entries(en.decisionJournal)
      .filter(([key]) => key.startsWith('patterns'))
      .map(([, value]) => value);
    expect(text.length).toBeGreaterThan(0);
    text.forEach((value) => expect(value).not.toMatch(ADVISORY));
  });
});
