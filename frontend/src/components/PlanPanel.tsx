import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import {
  getInvestmentPlan,
  saveAllocationPolicy,
  saveInvestmentPlan,
} from '../api';
import { localDateISO } from '../lib/date';
import { classLabel, goalPurposeLabel } from '../lib/planForm';
import type {
  InvestmentPlan,
  InvestmentPlanProfileRating,
  InvestmentPlanResponse,
  InvestmentPlanVehicle,
} from '../types';
import EmptyState from './EmptyState';
import PlanEditor from './PlanEditor';

const pct = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 });
const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
  maximumFractionDigits: 0,
});
const years = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 });

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

const errorStatus = (error: unknown): number | undefined =>
  (error as { status?: number } | null)?.status;

type LoadState =
  | { kind: 'loading' }
  | { kind: 'missing' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: InvestmentPlanResponse };

function useInvestmentPlan(owner: string, reloadToken: number) {
  const [state, setState] = useState<LoadState>({ kind: 'loading' });

  const load = useCallback(async () => {
    if (!owner) return;
    // Keep showing the current plan while refreshing after a targets change.
    setState((prev) => (prev.kind === 'ready' ? prev : { kind: 'loading' }));
    try {
      setState({ kind: 'ready', data: await getInvestmentPlan(owner) });
    } catch (err) {
      setState(
        errorStatus(err) === 404
          ? { kind: 'missing' }
          : { kind: 'error', message: errorText(err) }
      );
    }
  }, [owner]);

  // A different owner's plan must not linger while the new one loads.
  useEffect(() => {
    setState({ kind: 'loading' });
  }, [owner]);

  useEffect(() => {
    void load(); // errors are captured into state inside load
  }, [load, reloadToken]);

  return { state, setState, load };
}

function vehicleText(vehicles: InvestmentPlanVehicle[] | undefined): string {
  if (!vehicles?.length) return '—';
  return vehicles
    .map((v) =>
      v.ticker && v.note ? `${v.ticker} (${v.note})` : (v.ticker ?? v.note)
    )
    .join(', ');
}

function TargetTable({ plan }: { plan: InvestmentPlan }) {
  const { t } = useTranslation();
  return (
    <table
      className="mb-3 w-full border-collapse text-sm"
      aria-label={t('planPanel.planTarget')}
    >
      <thead>
        <tr>
          <th className="px-2 py-1 text-left">{t('planPanel.class')}</th>
          <th className="px-2 py-1 text-right">{t('planPanel.targetPct')}</th>
          <th className="px-2 py-1 text-left">{t('planPanel.vehicles')}</th>
        </tr>
      </thead>
      <tbody>
        {plan.target.map((row) => (
          <tr key={row.class}>
            <td className="px-2 py-1">{classLabel(row.class)}</td>
            <td className="px-2 py-1 text-right">
              {pct.format(row.weight_pct)}%
            </td>
            <td className="px-2 py-1">
              {vehicleText(plan.vehicles[row.class])}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function formatTargets(targets: Record<string, number>, t: TFunction): string {
  const entries = Object.entries(targets);
  if (!entries.length) return t('planPanel.noneSaved');
  return entries
    .map(([k, v]) => `${classLabel(k)} ${pct.format(v)}%`)
    .join(', ');
}

type Comparison = InvestmentPlanResponse['rebalance'];

/** Saves the plan target (in the policy's vocabulary) as the rebalance targets. */
function useCopyToRebalance(
  owner: string,
  comparison: Comparison,
  onCopied: () => Promise<void>
) {
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function copy() {
    setCopying(true);
    setError(null);
    try {
      await saveAllocationPolicy(owner, {
        targets: comparison.plan_targets,
        tolerance_pct: comparison.tolerance_pct,
      });
      await onCopied();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setCopying(false);
    }
  }

  return { copy, copying, error };
}

/**
 * Writes the rebalance targets (e.g. a just-applied strategy) into the plan
 * target as a new version, recording the change as a decision (#9815).
 */
function useUpdatePlanFromTargets(
  owner: string,
  plan: InvestmentPlan,
  weights: Record<string, number> | null | undefined,
  onUpdated: (data: InvestmentPlanResponse) => void,
  strategyName?: string
) {
  const { t } = useTranslation();
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function update() {
    if (!weights) return;
    setUpdating(true);
    setError(null);
    const today = localDateISO();
    const targets = formatTargets(weights, t);
    try {
      const data = await saveInvestmentPlan(owner, {
        ...plan,
        version: plan.version + 1,
        updated: today,
        target: Object.entries(weights).map(([cls, weight_pct]) => ({
          class: cls,
          weight_pct,
        })),
        decisions: [
          ...plan.decisions,
          {
            date: today,
            decision: strategyName
              ? t('planPanel.decisionSwitched', { name: strategyName, targets })
              : t('planPanel.decisionMatched', { targets }),
            alternatives: [],
          },
        ],
      });
      onUpdated(data);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setUpdating(false);
    }
  }

  return { update, updating, error };
}

const PRIMARY_BUTTON =
  'mt-2 rounded bg-blue-500 px-3 py-1 text-white disabled:opacity-50';

/** Offers to carry the rebalance targets (e.g. an applied strategy) into the plan. */
function UpdatePlanButton({
  owner,
  plan,
  comparison,
  onPlanUpdated,
  strategyName,
  label,
}: {
  owner: string;
  plan: InvestmentPlan;
  comparison: Comparison;
  onPlanUpdated: (data: InvestmentPlanResponse) => void;
  /** The strategy just applied, named in the recorded decision. */
  strategyName?: string;
  label: string;
}) {
  const { t } = useTranslation();
  const { update, updating, error } = useUpdatePlanFromTargets(
    owner,
    plan,
    comparison.rebalance_as_plan,
    onPlanUpdated,
    strategyName
  );
  if (!comparison.rebalance_as_plan) return null;
  return (
    <>
      <button
        type="button"
        onClick={() => void update()}
        disabled={updating}
        className={PRIMARY_BUTTON}
      >
        {updating ? t('planPanel.updatingPlan') : label}
      </button>
      {error && <p className="mt-1 break-words text-red-600">{error}</p>}
    </>
  );
}

/** Right after a strategy is applied: offers to switch the plan to it too (#9815). */
function AppliedStrategyPrompt({
  owner,
  plan,
  comparison,
  strategyName,
  onPlanUpdated,
  onDismiss,
}: {
  owner: string;
  plan: InvestmentPlan;
  comparison: Comparison;
  strategyName: string;
  onPlanUpdated: (data: InvestmentPlanResponse) => void;
  onDismiss: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="mb-3 text-sm"
      role="status"
      aria-label={t('planPanel.appliedAria')}
    >
      <p className="text-amber-700 dark:text-amber-300">
        {t('planPanel.appliedPrompt', { name: strategyName })}
      </p>
      <p>
        {t('planPanel.planLabel')} {formatTargets(comparison.plan_targets, t)}
      </p>
      <p>
        {strategyName}: {formatTargets(comparison.rebalance_targets, t)}
      </p>
      <div className="flex flex-wrap gap-2">
        <UpdatePlanButton
          owner={owner}
          plan={plan}
          comparison={comparison}
          onPlanUpdated={onPlanUpdated}
          strategyName={strategyName}
          label={t('planPanel.updatePlan')}
        />
        <button
          type="button"
          onClick={onDismiss}
          className="mt-2 rounded bg-gray-200 px-3 py-1 text-slate-900"
        >
          {t('planPanel.notNow')}
        </button>
      </div>
    </div>
  );
}

/**
 * Plan vs rebalance targets. Right after an active plan is saved with a
 * different target (`offerSync`), asks whether to update the rebalance
 * targets; otherwise reports the mismatch with a copy button (#9680).
 */
function RebalanceComparison({
  owner,
  plan,
  comparison,
  onCopied,
  onPlanUpdated,
  offerSync,
  onDismiss,
  appliedStrategy,
  onDismissApplied,
}: {
  owner: string;
  plan: InvestmentPlan;
  comparison: Comparison;
  onCopied: () => Promise<void>;
  onPlanUpdated: (data: InvestmentPlanResponse) => void;
  offerSync: boolean;
  onDismiss: () => void;
  appliedStrategy: string | null;
  onDismissApplied: () => void;
}) {
  const { t } = useTranslation();
  const { copy, copying, error } = useCopyToRebalance(
    owner,
    comparison,
    onCopied
  );

  if (comparison.matches) {
    return (
      <p className="mb-3 text-sm text-green-700 dark:text-green-400">
        {t('planPanel.targetsMatch')}
      </p>
    );
  }

  if (appliedStrategy && comparison.rebalance_as_plan) {
    return (
      <AppliedStrategyPrompt
        owner={owner}
        plan={plan}
        comparison={comparison}
        strategyName={appliedStrategy}
        onPlanUpdated={onPlanUpdated}
        onDismiss={onDismissApplied}
      />
    );
  }

  const prompt = offerSync && comparison.copy_supported;
  return (
    <div
      className="mb-3 text-sm"
      role="status"
      aria-label={t('planPanel.mismatchAria')}
    >
      <p className="text-amber-700 dark:text-amber-300">
        {prompt ? t('planPanel.updatePrompt') : t('planPanel.targetsDiffer')}
      </p>
      <p>
        {t('planPanel.planLabel')} {formatTargets(comparison.plan_targets, t)}
      </p>
      <p>
        {t('planPanel.rebalanceTargetsLabel')}{' '}
        {formatTargets(comparison.rebalance_targets, t)}
      </p>
      <div className="flex flex-wrap gap-2">
        {comparison.copy_supported && (
          <button
            type="button"
            onClick={() => void copy()}
            disabled={copying}
            className={PRIMARY_BUTTON}
          >
            {copying
              ? t('planPanel.updating')
              : prompt
                ? t('planPanel.updateTargets')
                : t('planPanel.copyTarget')}
          </button>
        )}
        {!prompt && (
          <UpdatePlanButton
            owner={owner}
            plan={plan}
            comparison={comparison}
            onPlanUpdated={onPlanUpdated}
            label={t('planPanel.updatePlanToTargets')}
          />
        )}
        {prompt && (
          <button
            type="button"
            onClick={onDismiss}
            className="mt-2 rounded bg-gray-200 px-3 py-1 text-slate-900"
          >
            {t('planPanel.notNow')}
          </button>
        )}
      </div>
      {!comparison.copy_supported && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {t('planPanel.perAssetClassNote')}
        </p>
      )}
      {error && <p className="mt-1 break-words text-red-600">{error}</p>}
    </div>
  );
}

function ListSection({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="mb-3">
      <h3 className="font-medium">{title}</h3>
      <ul className="list-disc pl-5 text-sm">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function ratingText(
  rating: InvestmentPlanProfileRating | undefined,
  t: TFunction
): string {
  if (!rating) return t('planPanel.notRecorded');
  return rating.note ? `${rating.level} — ${rating.note}` : rating.level;
}

function yearsToGoalText(value: number | undefined, t: TFunction): string {
  if (value == null) return '—';
  return value < 0
    ? t('planPanel.yearsAgo', { value: years.format(-value) })
    : years.format(value);
}

function GoalTable({ data }: { data: InvestmentPlanResponse }) {
  const { t } = useTranslation();
  const goals = data.plan.profile?.goals ?? [];
  if (!goals.length) return null;
  const toGo = new Map(
    (data.horizon?.goals ?? []).map((g) => [g.index, g.years_to_goal])
  );
  return (
    <table
      className="w-full border-collapse text-sm"
      aria-label={t('planPanel.planGoals')}
    >
      <thead>
        <tr>
          <th className="px-2 py-1 text-left">{t('planPanel.goal')}</th>
          <th className="px-2 py-1 text-left">{t('planPanel.purpose')}</th>
          <th className="px-2 py-1 text-left">{t('planPanel.targetDate')}</th>
          <th className="px-2 py-1 text-right">{t('planPanel.yearsToGo')}</th>
          <th className="px-2 py-1 text-right">{t('planPanel.amount')}</th>
          <th className="px-2 py-1 text-right">{t('planPanel.priority')}</th>
        </tr>
      </thead>
      <tbody>
        {goals.map((goal, i) => (
          <tr key={i}>
            <td className="px-2 py-1">
              {goal.name}
              {goal.note && (
                <span className="block text-xs text-slate-500 dark:text-slate-400">
                  {goal.note}
                </span>
              )}
            </td>
            <td className="px-2 py-1">{goalPurposeLabel(goal.purpose)}</td>
            <td className="px-2 py-1">{goal.target_date ?? '—'}</td>
            <td className="px-2 py-1 text-right">
              {yearsToGoalText(toGo.get(i), t)}
            </td>
            <td className="px-2 py-1 text-right">
              {goal.amount_gbp != null ? gbp.format(goal.amount_gbp) : '—'}
            </td>
            <td className="px-2 py-1 text-right">{goal.priority ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Owner-stated profile and goals (#9760), shown as recorded: no score or verdict. */
function ProfileSection({ data }: { data: InvestmentPlanResponse }) {
  const { t } = useTranslation();
  const { profile } = data.plan;
  if (!profile) return null;
  const age = data.horizon?.age;
  return (
    <div
      className="mb-3"
      aria-label={t('planPanel.profileAndGoals')}
      role="group"
    >
      <h3 className="font-medium">{t('planPanel.profileAndGoals')}</h3>
      <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">
        {t('planPanel.profileNote')}
      </p>
      <ul className="mb-2 text-sm">
        {age != null && (
          <li>
            <span className="font-medium">{t('planPanel.age')}</span> {age}
          </li>
        )}
        <li>
          <span className="font-medium">{t('planPanel.riskTolerance')}</span>{' '}
          {ratingText(profile.risk_tolerance, t)}
        </li>
        <li>
          <span className="font-medium">{t('planPanel.capacityForLoss')}</span>{' '}
          {ratingText(profile.capacity_for_loss, t)}
        </li>
      </ul>
      <GoalTable data={data} />
    </div>
  );
}

function PlanDetails({ plan }: { plan: InvestmentPlan }) {
  const { t } = useTranslation();
  const assumptions = plan.assumptions.map(
    (a) =>
      `${a.key.replace(/_/g, ' ')}${a.value != null ? `: ${String(a.value)}` : ''}${a.note ? ` — ${a.note}` : ''}`
  );
  const decisions = plan.decisions.map(
    (d) => `${d.date}: ${d.decision}${d.reason ? ` (${d.reason})` : ''}`
  );
  const evidence = plan.evidence.map(
    (e) =>
      `${e.metric}: ${String(e.value)}${e.basis ? ` — ${e.basis}` : ''} (${t('planPanel.asOf', { date: e.as_of })}${e.source ? `, ${e.source}` : ''})`
  );
  return (
    <>
      <ListSection title={t('planPanel.keyAssumptions')} items={assumptions} />
      <ListSection
        title={t('planPanel.openQuestions')}
        items={plan.open_questions}
      />
      <details className="mb-3">
        <summary className="cursor-pointer font-medium">
          {t('planPanel.decisionsAndEvidence', {
            decisions: decisions.length,
            evidence: evidence.length,
          })}
        </summary>
        <ListSection title={t('planPanel.decisions')} items={decisions} />
        <ListSection title={t('planPanel.evidence')} items={evidence} />
      </details>
      <p className="mb-1 text-sm">
        <span className="font-medium">{t('planPanel.nextReview')}</span>{' '}
        {plan.review.next_review ?? t('planPanel.notSet')}
      </p>
      <ListSection
        title={t('planPanel.reviewTriggers')}
        items={plan.review.triggers}
      />
    </>
  );
}

function PlanBody({
  owner,
  data,
  onCopied,
  onPlanUpdated,
  offerSync,
  onDismissSync,
  appliedStrategy,
  onDismissApplied,
}: {
  owner: string;
  data: InvestmentPlanResponse;
  onCopied: () => Promise<void>;
  onPlanUpdated: (data: InvestmentPlanResponse) => void;
  offerSync: boolean;
  onDismissSync: () => void;
  appliedStrategy: string | null;
  onDismissApplied: () => void;
}) {
  const { t } = useTranslation();
  const { plan } = data;
  return (
    <>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {plan.status} · {t('planPanel.version', { version: plan.version })} ·{' '}
        {t('planPanel.updated', { date: plan.updated })}
      </p>
      {plan.summary && <p className="mb-3">{plan.summary}</p>}
      <ProfileSection data={data} />
      {data.strategy && (
        <p className="mb-2 text-sm">
          <span className="font-medium">{t('planPanel.matchesStrategy')}</span>{' '}
          {data.strategy.name}
        </p>
      )}
      <TargetTable plan={plan} />
      <RebalanceComparison
        owner={owner}
        plan={plan}
        comparison={data.rebalance}
        onCopied={onCopied}
        onPlanUpdated={onPlanUpdated}
        offerSync={offerSync}
        onDismiss={onDismissSync}
        appliedStrategy={appliedStrategy}
        onDismissApplied={onDismissApplied}
      />
      {data.warnings.length > 0 && (
        <ul className="mb-3 list-disc pl-5 text-xs text-amber-700 dark:text-amber-300">
          {data.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <PlanDetails plan={plan} />
      <p className="mt-3 text-xs italic text-slate-500 dark:text-slate-400">
        {plan.disclaimer}
      </p>
    </>
  );
}

/**
 * The owner's investment plan record (#9547): their chosen target, the
 * assumptions and decisions behind it, and when to review it. The plan states
 * the owner's own decisions; attached analysis is information, not advice.
 */
export default function PlanPanel({
  owner,
  onTargetsCopied,
  reloadToken = 0,
  appliedStrategy = null,
}: {
  owner: string;
  onTargetsCopied?: () => Promise<void> | void;
  /** Bump to re-fetch the plan comparison after the rebalance targets change elsewhere. */
  reloadToken?: number;
  /** A strategy just applied on the page; `token` changes on every apply. */
  appliedStrategy?: { name: string; token: number } | null;
}) {
  const { t } = useTranslation();
  const { state, setState, load } = useInvestmentPlan(owner, reloadToken);
  const [editing, setEditing] = useState(false);
  // Set when an active plan was just saved with a target that differs from the rebalance targets.
  const [offerSync, setOfferSync] = useState(false);
  // Name of a just-applied strategy the plan could switch to as well.
  const [offerApplied, setOfferApplied] = useState<string | null>(null);

  useEffect(() => {
    setEditing(false);
    setOfferSync(false);
    setOfferApplied(null);
  }, [owner]);

  useEffect(() => {
    if (appliedStrategy) setOfferApplied(appliedStrategy.name);
  }, [appliedStrategy]);

  // Refresh the comparison even if the page's own reload fails; that error
  // still propagates to the copy button's error message.
  const handleCopied = async () => {
    try {
      await onTargetsCopied?.();
    } finally {
      await load();
    }
  };

  if (!owner) return null;
  const initial = state.kind === 'ready' ? state.data.plan : {};

  return (
    <section
      className="mb-6 rounded border p-4"
      aria-label={t('planPanel.investmentPlan')}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl">{t('planPanel.investmentPlan')}</h2>
        {!editing && state.kind === 'ready' && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="rounded bg-gray-200 px-2 py-1 text-sm text-slate-900"
          >
            {t('planPanel.editPlan')}
          </button>
        )}
      </div>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('planPanel.subtitle')}
      </p>
      {editing ? (
        <PlanEditor
          owner={owner}
          initial={initial}
          onSaved={(data) => {
            setState({ kind: 'ready', data });
            setEditing(false);
            setOfferSync(
              data.plan.status === 'active' && !data.rebalance.matches
            );
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          {state.kind === 'loading' && (
            <p className="text-sm text-slate-500">{t('planPanel.loading')}</p>
          )}
          {state.kind === 'error' && (
            <p className="break-words text-sm text-red-600">
              {t('planPanel.loadError', { message: state.message })}
            </p>
          )}
          {state.kind === 'missing' && (
            <EmptyState
              message={t('planPanel.noPlan', { owner })}
              actions={[
                {
                  label: t('planPanel.createPlan'),
                  onClick: () => setEditing(true),
                },
              ]}
            />
          )}
          {state.kind === 'ready' && (
            <PlanBody
              owner={owner}
              data={state.data}
              onCopied={handleCopied}
              onPlanUpdated={(data) => {
                setState({ kind: 'ready', data });
                setOfferApplied(null);
              }}
              offerSync={offerSync}
              onDismissSync={() => setOfferSync(false)}
              appliedStrategy={offerApplied}
              onDismissApplied={() => setOfferApplied(null)}
            />
          )}
        </>
      )}
    </section>
  );
}
