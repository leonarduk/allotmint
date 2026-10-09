import { describe, expect, it } from 'vitest';
import type { InvestmentPlan } from '@/types';
import {
  classLabel,
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

  it('reads the backend vehicle shorthand of bare ticker strings', () => {
    const vehicles = {
      long_gilts: 'GLTL.L',
      gold: ['SGLN.L', { note: 'or physical' }],
    } as unknown as InvestmentPlan['vehicles'];
    expect(fromPlan({ vehicles }).vehicles).toEqual([
      { class: 'long_gilts', ticker: 'GLTL.L', note: '' },
      { class: 'gold', ticker: 'SGLN.L', note: '' },
      { class: 'gold', ticker: '', note: 'or physical' },
    ]);
  });

  it('drops blank rows and blank optional fields', () => {
    const form = {
      ...emptyPlanForm(),
      assumptions: [{ key: '', value: '', note: ' ' }],
      decisions: [
        { id: '', date: '', decision: '', reason: '', alternatives: '' },
        // A carried-over journal id alone doesn't keep a row.
        { id: 'dj-1', date: '', decision: '', reason: '', alternatives: '' },
        {
          id: '',
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

  it('round-trips decision-journal ids unchanged (#10481)', () => {
    const logged: InvestmentPlan = {
      ...plan,
      decisions: [
        ...plan.decisions,
        {
          id: 'dj-0123456789ab',
          date: '2026-10-01',
          decision: 'Sold £10,000 of AAA.L',
          alternatives: ['Keep holding AAA.L'],
          reason: 'Owner reasoning',
        },
      ],
    };
    const out = toPlan(fromPlan(logged), 'alex', '2026-10-06');
    expect(JSON.parse(JSON.stringify(out.decisions))).toEqual(logged.decisions);
    expect(out.decisions[0].id).toBeUndefined();
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

  it('labels other_commodities as the sub-class and a lone legacy commodities as the class', () => {
    expect(classLabel('other_commodities')).toBe('Other commodities');
    expect(classLabel('commodities')).toBe('Commodity');
  });

  it('totals only numeric target weights', () => {
    expect(
      targetTotal([
        { class: 'equity', weight: '60' },
        { class: 'gold', weight: '' },
        { class: 'cash', weight: '12.5' },
        { class: 'other_commodities', weight: '5abc' },
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
  describe('profile (#9760)', () => {
    const profile: InvestmentPlan['profile'] = {
      risk_tolerance: { level: 'medium', note: 'can sit through a 20% fall' },
      capacity_for_loss: { level: 'high' },
      goals: [
        {
          name: 'Joe university',
          purpose: 'education',
          target_date: '2033-09-01',
          amount_gbp: 30000,
          priority: 1,
          note: 'fees and rent',
        },
        { name: 'Rainy day', purpose: 'general_wealth' },
      ],
    };

    it('round-trips a profile through the form', () => {
      const withProfile = { ...plan, profile };
      expect(toPlan(fromPlan(withProfile), 'alex', '2026-10-06')).toEqual({
        ...withProfile,
        updated: '2026-10-06',
      });
    });

    it('omits the profile when nothing is recorded', () => {
      const form = fromPlan(plan);
      expect(form.risk_tolerance).toEqual({ level: '', note: '' });
      expect(form.goals).toEqual([]);
      const out = toPlan(
        {
          ...form,
          goals: [
            {
              name: ' ',
              purpose: 'retirement',
              target_date: '',
              amount: '',
              priority: '',
              note: '',
            },
          ],
        },
        'alex',
        '2026-10-06'
      );
      expect(out.profile).toBeUndefined();
      expect(JSON.parse(JSON.stringify(out))).not.toHaveProperty('profile');
    });

    it('saves a rating alone and drops blank goal fields', () => {
      const out = toPlan(
        {
          ...emptyPlanForm(),
          capacity_for_loss: { level: 'low', note: ' ' },
          goals: [
            {
              name: 'Drawdown',
              purpose: 'retirement',
              target_date: '2033-04-06',
              amount: '',
              priority: '2',
              note: '',
            },
          ],
        },
        'alex',
        '2026-10-06'
      );
      expect(JSON.parse(JSON.stringify(out.profile))).toEqual({
        capacity_for_loss: { level: 'low' },
        goals: [
          {
            name: 'Drawdown',
            purpose: 'retirement',
            target_date: '2033-04-06',
            priority: 2,
          },
        ],
      });
    });

    it('reports profile problems the backend would reject', () => {
      const goal = {
        name: '',
        purpose: 'other' as const,
        target_date: '',
        amount: '-5',
        priority: '1.5',
        note: '',
      };
      expect(
        formErrors({
          ...emptyPlanForm(),
          risk_tolerance: { level: '', note: 'cautious' },
          goals: [goal],
        })
      ).toEqual([
        'Choose a risk tolerance level to go with its note.',
        'Goal 1 needs a name.',
        'Goal 1 amount must be a number of at least 0.',
        'Goal 1 priority must be a whole number of at least 1.',
      ]);
    });
  });
});
