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
  // PlanBriefCard (#10475) renders inside the plan; no brief saved yet.
  getLatestPlanBrief: vi
    .fn()
    .mockRejectedValue(Object.assign(new Error('none'), { status: 404 })),
  getPlanBrief: vi.fn(),
  listPlanBriefs: vi.fn(),
  runPlanBrief: vi.fn(),
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

  it('updates the plan target to match the rebalance targets', async () => {
    const response = makeResponse({
      rebalance_targets: { equity: 80, intermediate_gilts: 20 },
      rebalance_as_plan: { equity: 80, intermediate_gilts: 20 },
    });
    mockGetInvestmentPlan.mockResolvedValue(response);
    const updated = makeResponse({ matches: true });
    updated.plan = {
      ...updated.plan,
      version: 2,
      target: [
        { class: 'equity', weight_pct: 80 },
        { class: 'intermediate_gilts', weight_pct: 20 },
      ],
    };
    mockSaveInvestmentPlan.mockResolvedValue(updated);
    render(<PlanPanel owner="alex" />);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Update plan to match rebalance targets',
      })
    );

    await waitFor(() =>
      expect(
        screen.getByText('Your rebalance targets match this plan.')
      ).toBeInTheDocument()
    );
    const [owner, saved] = mockSaveInvestmentPlan.mock.calls[0];
    expect(owner).toBe('alex');
    expect(saved.version).toBe(2);
    expect(saved.target).toEqual([
      { class: 'equity', weight_pct: 80 },
      { class: 'intermediate_gilts', weight_pct: 20 },
    ]);
    expect(saved.summary).toBe(response.plan.summary);
    expect(saved.decisions.at(-1).decision).toMatch(
      /match rebalance targets: Equity 80%, Intermediate gilts 20%/
    );
  });

  it('offers to switch the plan to a just-applied strategy', async () => {
    const rebalance = {
      rebalance_targets: { equity: 80, intermediate_gilts: 20 },
      rebalance_as_plan: { equity: 80, intermediate_gilts: 20 },
    };
    mockGetInvestmentPlan.mockResolvedValue(makeResponse(rebalance));
    mockSaveInvestmentPlan.mockResolvedValue(makeResponse({ matches: true }));
    const { rerender } = render(<PlanPanel owner="alex" />);
    await screen.findByText('Your rebalance targets differ from this plan.');

    rerender(
      <PlanPanel owner="alex" appliedStrategy={{ name: '80/20', token: 1 }} />
    );
    expect(
      await screen.findByText(
        'You applied 80/20. Also update your investment plan to match?'
      )
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Update plan' }));

    await waitFor(() =>
      expect(
        screen.getByText('Your rebalance targets match this plan.')
      ).toBeInTheDocument()
    );
    const saved = mockSaveInvestmentPlan.mock.calls[0][1];
    expect(saved.target).toEqual([
      { class: 'equity', weight_pct: 80 },
      { class: 'intermediate_gilts', weight_pct: 20 },
    ]);
    expect(saved.decisions.at(-1).decision).toBe(
      'Switched to the 80/20 strategy: Equity 80%, Intermediate gilts 20%'
    );
  });

  it('lets the applied-strategy prompt be dismissed', async () => {
    mockGetInvestmentPlan.mockResolvedValue(
      makeResponse({ rebalance_as_plan: { equity: 100 } })
    );
    render(
      <PlanPanel
        owner="alex"
        appliedStrategy={{ name: '100% equity', token: 1 }}
      />
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Not now' }));
    expect(
      screen.getByText('Your rebalance targets differ from this plan.')
    ).toBeInTheDocument();
    expect(mockSaveInvestmentPlan).not.toHaveBeenCalled();
  });

  it('hides the update-plan button when the targets have no plan classes', async () => {
    mockGetInvestmentPlan.mockResolvedValue(
      makeResponse({ rebalance_as_plan: null })
    );
    render(<PlanPanel owner="alex" />);
    await screen.findByText('Your rebalance targets differ from this plan.');
    expect(
      screen.queryByRole('button', { name: /Update plan/ })
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

    async function saveReturning(
      status: 'active' | 'draft' | 'superseded',
      matches = false
    ) {
      // A non-default tolerance proves the copy keeps the saved policy's band.
      const response = makeResponse({
        copy_supported: true,
        plan_targets,
        tolerance_pct: 3.5,
      });
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
          tolerance_pct: 3.5,
        })
      );
    });

    it('shows a match once the update is saved and reloaded', async () => {
      mockSaveAllocationPolicy.mockResolvedValue({});
      await saveReturning('active');
      const onReload = makeResponse({ copy_supported: true, plan_targets });
      mockGetInvestmentPlan.mockResolvedValue({
        ...onReload,
        rebalance: { ...onReload.rebalance, matches: true },
      });

      fireEvent.click(
        screen.getByRole('button', { name: 'Update rebalance targets' })
      );
      expect(
        await screen.findByText('Your rebalance targets match this plan.')
      ).toBeInTheDocument();
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

    it.each(['draft', 'superseded'] as const)(
      'does not prompt for a %s plan',
      async (status) => {
        await saveReturning(status);
        expect(
          screen.queryByText(
            'Update your rebalance targets to match this plan?'
          )
        ).not.toBeInTheDocument();
        expect(
          screen.getByText('Your rebalance targets differ from this plan.')
        ).toBeInTheDocument();
      }
    );

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
  describe('profile and goals (#9760)', () => {
    const profile: InvestmentPlanResponse['plan']['profile'] = {
      risk_tolerance: { level: 'medium', note: 'can sit through a 20% fall' },
      capacity_for_loss: { level: 'low' },
      goals: [
        {
          name: 'Joe university',
          purpose: 'education',
          target_date: '2033-09-01',
          amount_gbp: 30000,
          priority: 1,
        },
        { name: 'Rainy day', purpose: 'general_wealth' },
      ],
    };

    function withProfile(): InvestmentPlanResponse {
      const response = makeResponse();
      return {
        ...response,
        plan: { ...response.plan, profile },
        horizon: {
          age: 50,
          goals: [{ index: 0, name: 'Joe university', years_to_goal: 6.9 }],
        },
      };
    }

    it('shows the recorded profile with derived age and years to go', async () => {
      mockGetInvestmentPlan.mockResolvedValue(withProfile());
      render(<PlanPanel owner="alex" />);

      const section = await screen.findByRole('group', {
        name: 'Profile and goals',
      });
      expect(section).toHaveTextContent('Age: 50');
      expect(section).toHaveTextContent(
        'Risk tolerance: medium — can sit through a 20% fall'
      );
      expect(section).toHaveTextContent('Capacity for loss: low');
      expect(section).toHaveTextContent(/not an assessment of suitability/);
      const rows = screen
        .getByRole('table', { name: 'Plan goals' })
        .querySelectorAll('tbody tr');
      expect(rows[0]).toHaveTextContent(
        'Joe universityEducation2033-09-016.9£30,0001'
      );
      expect(rows[1]).toHaveTextContent('Rainy dayGeneral wealth————');
      expect(screen.getByText(/not regulated advice/)).toBeInTheDocument();
    });

    it('shows a goal date that has passed as years ago', async () => {
      const response = withProfile();
      mockGetInvestmentPlan.mockResolvedValue({
        ...response,
        horizon: {
          age: 50,
          goals: [{ index: 0, name: 'Joe university', years_to_goal: -1.5 }],
        },
      });
      render(<PlanPanel owner="alex" />);
      const table = await screen.findByRole('table', { name: 'Plan goals' });
      expect(table.querySelector('tbody tr')).toHaveTextContent('1.5 ago');
    });

    it('carries the profile through the raw JSON view', async () => {
      mockGetInvestmentPlan.mockResolvedValue(withProfile());
      render(<PlanPanel owner="alex" />);
      fireEvent.click(await screen.findByRole('button', { name: 'Edit plan' }));
      fireEvent.click(screen.getByRole('button', { name: 'Edit as JSON' }));

      const editor = screen.getByLabelText('Plan JSON') as HTMLTextAreaElement;
      const json = JSON.parse(editor.value);
      expect(json.profile.goals[0].name).toBe('Joe university');
      json.profile.goals[0].name = 'Joe degree';
      fireEvent.change(editor, { target: { value: JSON.stringify(json) } });
      fireEvent.click(screen.getByRole('button', { name: 'Back to form' }));

      expect(screen.getByLabelText('Goal 1')).toHaveValue('Joe degree');
      expect(screen.getByLabelText('Risk tolerance level')).toHaveValue(
        'medium'
      );
    });

    it('omits the section for a plan without a profile', async () => {
      mockGetInvestmentPlan.mockResolvedValue(makeResponse());
      render(<PlanPanel owner="alex" />);
      await screen.findByText('40/20/20/20 without small-value');
      expect(
        screen.queryByRole('group', { name: 'Profile and goals' })
      ).not.toBeInTheDocument();
    });

    it('edits the profile in the form and saves it', async () => {
      mockGetInvestmentPlan.mockResolvedValue(makeResponse());
      mockSaveInvestmentPlan.mockResolvedValue(withProfile());
      render(<PlanPanel owner="alex" />);
      fireEvent.click(await screen.findByRole('button', { name: 'Edit plan' }));

      fireEvent.change(screen.getByLabelText('Risk tolerance level'), {
        target: { value: 'medium' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Add goal' }));
      fireEvent.change(screen.getByLabelText('Goal 1'), {
        target: { value: 'Joe university' },
      });
      fireEvent.change(screen.getByLabelText('Goal purpose 1'), {
        target: { value: 'education' },
      });
      fireEvent.change(screen.getByLabelText('Goal target date 1'), {
        target: { value: '2033-09-01' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));

      await screen.findByRole('group', { name: 'Profile and goals' });
      const saved = mockSaveInvestmentPlan.mock.calls[0][1];
      expect(JSON.parse(JSON.stringify(saved.profile))).toEqual({
        risk_tolerance: { level: 'medium' },
        goals: [
          {
            name: 'Joe university',
            purpose: 'education',
            target_date: '2033-09-01',
          },
        ],
      });
    });
  });
});
