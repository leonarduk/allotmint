import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanBrief } from '@/types';
import PlanBriefCard from '@/components/PlanBriefCard';

const mockGetLatest = vi.hoisted(() => vi.fn());
const mockGetOne = vi.hoisted(() => vi.fn());
const mockList = vi.hoisted(() => vi.fn());
const mockRun = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getLatestPlanBrief: mockGetLatest,
  getPlanBrief: mockGetOne,
  listPlanBriefs: mockList,
  runPlanBrief: mockRun,
}));

const DISCLAIMER =
  "Owner's own decisions; attached analysis is historical information, not regulated advice.";

function makeBrief(overrides: Partial<PlanBrief> = {}): PlanBrief {
  return {
    id: 'b2',
    owner: 'alex',
    as_of: '2026-10-09',
    generated_at: '2026-10-09T08:00:00+00:00',
    drift: {
      basis: 'plan',
      tolerance_pct: 5,
      total_value_gbp: 100000,
      rows: [
        {
          class: 'equity',
          label: 'Equity',
          current_value_gbp: 66000,
          current_pct: 66,
          target_pct: 60,
          drift_pp: 6,
          drift_gbp: 6000,
          status: 'over',
        },
        {
          class: 'cash',
          label: 'Cash',
          current_value_gbp: 4000,
          current_pct: 4,
          target_pct: 0,
          drift_pp: 4,
          drift_gbp: 4000,
          status: 'in_band',
        },
      ],
      out_of_band: ['equity'],
      rebalance_targets_match: false,
    },
    cash: [
      {
        account_id: 'isa',
        account: 'ISA',
        cash_gbp: 4000,
        uninvested_since: '2026-09-18',
        days_uninvested: 21,
      },
    ],
    stale_evidence: [
      { metric: 'gilt_20y_yield', as_of: '2025-11-01', age_days: 342 },
    ],
    review: {
      next_review: '2026-10-01',
      due: true,
      days_overdue: 8,
      open_questions: [],
    },
    changes: {
      since: '2026-09-09',
      contributions_gbp: 4000,
      withdrawals_gbp: 0,
      purchases_gbp: 0,
      sales_gbp: 0,
      big_movers: [],
    },
    triggers: [
      {
        trigger: 'Bank Rate below 3%',
        verdict: 'fired',
        reason: 'Bank Rate is 2.75%.',
        evidence: [
          {
            tool: 'get_market_rates',
            field: 'latest.bank_rate.value',
            value: 2.75,
            source: 'Bank of England IADB',
            as_of: '2026-10-08',
          },
        ],
      },
    ],
    prose: 'Equity is 6.0pp above its 60% target (£6,000).',
    prose_source: 'agent',
    disclaimer: DISCLAIMER,
    ...overrides,
  };
}

describe('PlanBriefCard', () => {
  beforeEach(() => {
    mockGetLatest.mockReset();
    mockGetOne.mockReset();
    mockList.mockReset();
    mockRun.mockReset();
  });

  it('renders the latest brief: drift, triggers, review due, cash and disclaimer', async () => {
    mockGetLatest.mockResolvedValue(makeBrief());
    render(<PlanBriefCard owner="alex" />);

    expect(
      await screen.findByText(/6\.0pp above its 60% target/)
    ).toBeInTheDocument();
    expect(mockGetLatest).toHaveBeenCalledWith('alex');
    const equityRow = screen.getByText('Equity').closest('tr');
    expect(equityRow).toHaveAttribute('data-status', 'over');
    expect(equityRow).toHaveTextContent('+6.0pp');
    expect(equityRow).toHaveTextContent('+£6,000');
    expect(screen.getByText('Cash').closest('tr')).toHaveAttribute(
      'data-status',
      'in_band'
    );
    expect(screen.getByText('Fired')).toBeInTheDocument();
    expect(screen.getByText(/Bank of England IADB/)).toBeInTheDocument();
    expect(screen.getByText(/Review due/)).toBeInTheDocument();
    expect(screen.getByText(/21 days with no purchase/)).toBeInTheDocument();
    expect(screen.getByText(/differ from the plan target/)).toBeInTheDocument();
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument();
  });

  it('shows an empty state on 404 and runs a brief on demand', async () => {
    mockGetLatest.mockRejectedValue(
      Object.assign(new Error('not found'), { status: 404 })
    );
    mockRun.mockResolvedValue(makeBrief());
    render(<PlanBriefCard owner="alex" />);

    expect(await screen.findByText(/No brief yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Run brief now' }));

    await waitFor(() => expect(mockRun).toHaveBeenCalledWith('alex'));
    expect(await screen.findByText(/6\.0pp above/)).toBeInTheDocument();
  });

  it('reports a load error other than 404', async () => {
    mockGetLatest.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 500 })
    );
    render(<PlanBriefCard owner="alex" />);
    expect(
      await screen.findByText(/Could not load the brief: boom/)
    ).toBeInTheDocument();
  });

  it('lists earlier briefs and opens one', async () => {
    mockGetLatest.mockResolvedValue(makeBrief());
    mockList.mockResolvedValue({
      owner: 'alex',
      briefs: [
        {
          id: 'b2',
          as_of: '2026-10-09',
          generated_at: '',
          total_value_gbp: 100000,
          out_of_band: ['equity'],
          triggers_fired: 1,
          review_due: true,
        },
        {
          id: 'b1',
          as_of: '2026-09-01',
          generated_at: '',
          total_value_gbp: 95000,
          out_of_band: [],
          triggers_fired: 0,
          review_due: false,
        },
      ],
    });
    mockGetOne.mockResolvedValue(
      makeBrief({
        id: 'b1',
        as_of: '2026-09-01',
        prose: 'Every class is within the 5pp band of its target.',
      })
    );
    render(<PlanBriefCard owner="alex" />);

    fireEvent.click(
      await screen.findByRole('button', { name: 'Earlier briefs' })
    );
    fireEvent.click(await screen.findByRole('button', { name: '2026-09-01' }));

    await waitFor(() => expect(mockGetOne).toHaveBeenCalledWith('alex', 'b1'));
    expect(
      await screen.findByText(/Every class is within/)
    ).toBeInTheDocument();
  });
});
