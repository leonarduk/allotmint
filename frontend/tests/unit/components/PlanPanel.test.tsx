import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { InvestmentPlanResponse } from '@/types';
import PlanPanel from '@/components/PlanPanel';

const mockGetInvestmentPlan = vi.hoisted(() => vi.fn());
const mockSaveInvestmentPlan = vi.hoisted(() => vi.fn());
const mockSaveAllocationPolicy = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getInvestmentPlan: mockGetInvestmentPlan,
  saveInvestmentPlan: mockSaveInvestmentPlan,
  saveAllocationPolicy: mockSaveAllocationPolicy,
}));

function makeResponse(
  rebalance: Partial<InvestmentPlanResponse['rebalance']> = {}
): InvestmentPlanResponse {
  return {
    plan: {
      owner: 'alex',
      version: 1,
      updated: '2026-10-06',
      status: 'draft',
      summary: '40/20/20/20 without small-value',
      target: [
        { class: 'equity', weight_pct: 40 },
        { class: 'long_gilts', weight_pct: 40 },
        { class: 'gold', weight_pct: 20 },
      ],
      vehicles: {
        long_gilts: [{ ticker: 'GLTL.L' }],
        equity: [{ note: 'global fund to be chosen' }],
      },
      assumptions: [{ key: 'retirement_age', value: 58, note: 'about 2033' }],
      decisions: [
        { date: '2026-10-06', decision: 'No small-value', alternatives: [] },
      ],
      open_questions: ['Lump sum or phase in?'],
      evidence: [{ as_of: '2026-10-06', metric: 'US CAPE', value: 40.6 }],
      review: { next_review: '2027-10-06', triggers: ['drift > 5pp'] },
      disclaimer:
        "Owner's own decisions; attached analysis is historical information, not regulated advice.",
    },
    warnings: [],
    rebalance: {
      rebalance_targets: { equity: 60, bond: 40 },
      tolerance_pct: 5,
      plan_targets: { equity: 40, bond: 40, commodity: 20 },
      matches: false,
      copy_supported: false,
      ...rebalance,
    },
  };
}

describe('PlanPanel', () => {
  beforeEach(() => {
    mockGetInvestmentPlan.mockReset();
    mockSaveInvestmentPlan.mockReset();
    mockSaveAllocationPolicy.mockReset();
  });

  it('shows summary, target, assumptions, next review and disclaimer', async () => {
    mockGetInvestmentPlan.mockResolvedValue(makeResponse());
    render(<PlanPanel owner="alex" />);

    expect(
      await screen.findByText('40/20/20/20 without small-value')
    ).toBeInTheDocument();
    expect(mockGetInvestmentPlan).toHaveBeenCalledWith('alex');
    expect(screen.getByText('Long gilts')).toBeInTheDocument();
    expect(screen.getByText('GLTL.L')).toBeInTheDocument();
    expect(screen.getByText('global fund to be chosen')).toBeInTheDocument();
    expect(
      screen.getByText('retirement age: 58 — about 2033')
    ).toBeInTheDocument();
    expect(screen.getByText('Lump sum or phase in?')).toBeInTheDocument();
    expect(screen.getByText('2027-10-06')).toBeInTheDocument();
    expect(screen.getByText(/not regulated advice/)).toBeInTheDocument();
    expect(screen.getByText(/Your own decisions/)).toBeInTheDocument();
  });

  it('shows an empty state when no plan is saved', async () => {
    mockGetInvestmentPlan.mockRejectedValue(
      Object.assign(new Error('No investment plan saved for alex'), {
        status: 404,
      })
    );
    render(<PlanPanel owner="alex" />);

    expect(
      await screen.findByText('No investment plan saved for alex yet.')
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Create plan' }));
    expect(screen.getByLabelText('Target class 1')).toHaveValue('equity');
    expect(screen.getByLabelText('Target weight % 1')).toHaveValue(100);
    fireEvent.click(screen.getByRole('button', { name: 'Edit as JSON' }));
    expect(
      (screen.getByLabelText('Plan JSON') as HTMLTextAreaElement).value
    ).toContain('"owner": "alex"');
  });

  it('reports other load errors without breaking', async () => {
    mockGetInvestmentPlan.mockRejectedValue(new Error('HTTP 500'));
    render(<PlanPanel owner="alex" />);
    expect(
      await screen.findByText('Unable to load the investment plan: HTTP 500')
    ).toBeInTheDocument();
  });

  it('shows a mismatch as text when copying is not supported', async () => {
    mockGetInvestmentPlan.mockResolvedValue(makeResponse());
    render(<PlanPanel owner="alex" />);

    expect(
      await screen.findByText('Your rebalance targets differ from this plan.')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Plan: Equity 40%, Bond 40%, Commodity 20%')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Rebalance targets: Equity 60%, Bond 40%')
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Copy plan target/ })
    ).not.toBeInTheDocument();
  });

  it('copies the plan target to the rebalance targets when supported', async () => {
    const plan_targets = { equity: 40, long_gilts: 40, gold: 20 };
    mockGetInvestmentPlan.mockResolvedValue(
      makeResponse({ copy_supported: true, plan_targets })
    );
    mockSaveAllocationPolicy.mockResolvedValue({
      targets: plan_targets,
      tolerance_pct: 5,
    });
    const onTargetsCopied = vi.fn();
    render(<PlanPanel owner="alex" onTargetsCopied={onTargetsCopied} />);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Copy plan target to rebalance targets',
      })
    );
    await waitFor(() => expect(onTargetsCopied).toHaveBeenCalled());
    expect(mockSaveAllocationPolicy).toHaveBeenCalledWith('alex', {
      targets: plan_targets,
      tolerance_pct: 5,
    });
    expect(mockGetInvestmentPlan).toHaveBeenCalledTimes(2);
  });

  it('refreshes the comparison even if the page reload fails after copying', async () => {
    const plan_targets = { equity: 40, long_gilts: 40, gold: 20 };
    mockGetInvestmentPlan.mockResolvedValue(
      makeResponse({ copy_supported: true, plan_targets })
    );
    mockSaveAllocationPolicy.mockResolvedValue({
      targets: plan_targets,
      tolerance_pct: 5,
    });
    const onTargetsCopied = vi
      .fn()
      .mockRejectedValue(new Error('reload failed'));
    render(<PlanPanel owner="alex" onTargetsCopied={onTargetsCopied} />);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Copy plan target to rebalance targets',
      })
    );
    await waitFor(() => expect(mockGetInvestmentPlan).toHaveBeenCalledTimes(2));
  });

  it('says so when the rebalance targets match', async () => {
    mockGetInvestmentPlan.mockResolvedValue(makeResponse({ matches: true }));
    render(<PlanPanel owner="alex" />);
    expect(
      await screen.findByText('Your rebalance targets match this plan.')
    ).toBeInTheDocument();
  });

  it('saves edits through the raw JSON view and surfaces validation errors', async () => {
    const response = makeResponse();
    mockGetInvestmentPlan.mockResolvedValue(response);
    mockSaveInvestmentPlan
      .mockRejectedValueOnce(
        new Error('target: Target weights must sum to 100%, got 90%')
      )
      .mockResolvedValueOnce({
        ...response,
        plan: { ...response.plan, summary: 'Updated summary' },
      });
    render(<PlanPanel owner="alex" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Edit plan' }));
    fireEvent.click(screen.getByRole('button', { name: 'Edit as JSON' }));
    const editor = screen.getByLabelText('Plan JSON');
    fireEvent.change(editor, { target: { value: '{not json' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));
    expect(await screen.findByText(/Invalid JSON/)).toBeInTheDocument();
    expect(mockSaveInvestmentPlan).not.toHaveBeenCalled();

    fireEvent.change(editor, {
      target: { value: JSON.stringify(response.plan) },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));
    expect(await screen.findByText(/must sum to 100%/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));
    expect(await screen.findByText('Updated summary')).toBeInTheDocument();
    expect(mockSaveInvestmentPlan).toHaveBeenLastCalledWith(
      'alex',
      response.plan
    );
  });

  describe('after saving a plan (#9680)', () => {
    const plan_targets = { equity: 40, long_gilts: 40, gold: 20 };

    async function saveReturning(status: 'active' | 'draft', matches = false) {
      const response = makeResponse({ copy_supported: true, plan_targets });
      mockGetInvestmentPlan.mockResolvedValue(response);
      mockSaveInvestmentPlan.mockResolvedValue({
        ...response,
        plan: { ...response.plan, status },
        rebalance: { ...response.rebalance, matches },
      });
      render(<PlanPanel owner="alex" />);
      fireEvent.click(await screen.findByRole('button', { name: 'Edit plan' }));
      fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));
      await screen.findByRole('button', { name: 'Edit plan' });
    }

    it('offers to update the rebalance targets for an active plan', async () => {
      mockSaveAllocationPolicy.mockResolvedValue({});
      await saveReturning('active');

      expect(
        screen.getByText('Update your rebalance targets to match this plan?')
      ).toBeInTheDocument();
      fireEvent.click(
        screen.getByRole('button', { name: 'Update rebalance targets' })
      );
      await waitFor(() =>
        expect(mockSaveAllocationPolicy).toHaveBeenCalledWith('alex', {
          targets: plan_targets,
          tolerance_pct: 5,
        })
      );
    });

    it('falls back to the plain mismatch after "Not now"', async () => {
      await saveReturning('active');
      fireEvent.click(screen.getByRole('button', { name: 'Not now' }));

      expect(
        screen.getByText('Your rebalance targets differ from this plan.')
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', {
          name: 'Copy plan target to rebalance targets',
        })
      ).toBeInTheDocument();
      expect(mockSaveAllocationPolicy).not.toHaveBeenCalled();
    });

    it('does not prompt for a draft plan', async () => {
      await saveReturning('draft');
      expect(
        screen.queryByText('Update your rebalance targets to match this plan?')
      ).not.toBeInTheDocument();
      expect(
        screen.getByText('Your rebalance targets differ from this plan.')
      ).toBeInTheDocument();
    });

    it('does not prompt when the targets already match', async () => {
      await saveReturning('active', true);
      expect(
        screen.getByText('Your rebalance targets match this plan.')
      ).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: 'Not now' })
      ).not.toBeInTheDocument();
    });
  });
});
