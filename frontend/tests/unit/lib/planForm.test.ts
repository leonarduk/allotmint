import { describe, expect, it } from 'vitest';
import type { InvestmentPlan } from '@/types';
import {
  emptyPlanForm,
  formErrors,
  fromPlan,
  parseNumberOrText,
  parseScalar,
  targetTotal,
  toPlan,
} from '@/lib/planForm';

const plan: InvestmentPlan = {
  owner: 'alex',
  version: 2,
  updated: '2026-01-01',
  status: 'active',
  summary: '60/40',
  target: [
    { class: 'equity', weight_pct: 60 },
    { class: 'long_gilts', weight_pct: 40 },
  ],
  vehicles: {
    equity: [{ ticker: 'VWRP.L' }, { note: 'small-cap fund tbc' }],
    gold: [{ ticker: 'SGLN.L', note: 'not targeted yet' }],
  },
  assumptions: [
    { key: 'retirement_age', value: 58, note: 'about 2033' },
    { key: 'has_db_pension', value: true },
    { key: 'risk', value: 'moderate' },
  ],
  decisions: [
    {
      date: '2026-01-01',
      decision: 'No small-value',
      alternatives: ['ZPRV', 'ZPRX'],
      reason: 'Costs',
    },
  ],
  open_questions: ['Lump sum or phase in?'],
  evidence: [
    { as_of: '2026-01-01', metric: 'US CAPE', value: 40.6, source: 'Shiller' },
  ],
  review: { next_review: '2027-01-01', triggers: ['drift > 5pp'] },
  disclaimer: 'Own decisions.',
};

describe('planForm', () => {
  it('round-trips a plan through the form, stamping owner and updated', () => {
    expect(toPlan(fromPlan(plan), 'alex', '2026-10-06')).toEqual({
      ...plan,
      updated: '2026-10-06',
    });
  });

  it('keeps vehicles for classes that are not in the target', () => {
    const out = toPlan(fromPlan(plan), 'alex', '2026-10-06');
    expect(out.vehicles.gold).toEqual([
      { ticker: 'SGLN.L', note: 'not targeted yet' },
    ]);
  });

  it('drops blank rows and blank optional fields', () => {
    const form = {
      ...emptyPlanForm(),
      assumptions: [{ key: '', value: '', note: ' ' }],
      decisions: [
        { date: '', decision: '', reason: '', alternatives: '' },
        {
          date: '2026-10-06',
          decision: 'Hold',
          reason: '',
          alternatives: 'a\n\n b ',
        },
      ],
      vehicles: [{ class: 'equity', ticker: '', note: '' }],
      open_questions: [{ text: '  ' }, { text: 'Why?' }],
    };
    const out = toPlan(form, 'alex', '2026-10-06');
    expect(out.assumptions).toEqual([]);
    expect(out.vehicles).toEqual({});
    expect(out.decisions).toEqual([
      {
        date: '2026-10-06',
        decision: 'Hold',
        reason: undefined,
        alternatives: ['a', 'b'],
      },
    ]);
    expect(out.open_questions).toEqual(['Why?']);
    expect(out.review.next_review).toBeUndefined();
    expect(out).not.toHaveProperty('disclaimer');
  });

  it('parses scalars into their JSON types', () => {
    expect(parseScalar(' 58 ')).toBe(58);
    expect(parseScalar('-1.5')).toBe(-1.5);
    expect(parseScalar('true')).toBe(true);
    expect(parseScalar('false')).toBe(false);
    expect(parseScalar('58 years')).toBe('58 years');
    expect(parseScalar('')).toBeUndefined();
  });

  it('keeps true/false as text in evidence values', () => {
    expect(parseNumberOrText('true')).toBe('true');
    expect(parseNumberOrText(' 40.6 ')).toBe(40.6);
    expect(parseNumberOrText(' ')).toBeUndefined();
    const out = toPlan(
      {
        ...emptyPlanForm(),
        evidence: [
          {
            as_of: '2026-10-06',
            metric: 'Hedged',
            value: 'true',
            basis: '',
            source: '',
          },
        ],
      },
      'alex',
      '2026-10-06'
    );
    expect(out.evidence[0].value).toBe('true');
  });

  it('totals only numeric target weights', () => {
    expect(
      targetTotal([
        { class: 'equity', weight: '60' },
        { class: 'gold', weight: '' },
        { class: 'cash', weight: '12.5' },
        { class: 'commodities', weight: '5abc' },
      ])
    ).toBe(72.5);
  });

  it('reports a target that does not sum to 100%', () => {
    expect(
      formErrors({
        ...emptyPlanForm(),
        target: [
          { class: 'equity', weight: '60' },
          { class: 'gold', weight: '30' },
        ],
      })
    ).toEqual(['Target weights must sum to 100%, got 90%.']);
  });

  it('reports bad version, non-numeric weights and duplicate classes', () => {
    expect(formErrors(emptyPlanForm())).toEqual([]);
    expect(
      formErrors({
        ...emptyPlanForm(),
        version: '0',
        target: [
          { class: 'equity', weight: 'abc' },
          { class: 'equity', weight: '10' },
        ],
      })
    ).toEqual([
      'Version must be a whole number of at least 1.',
      'Target weight for Equity is not a number.',
      'Equity appears more than once in the target.',
    ]);
  });
});
