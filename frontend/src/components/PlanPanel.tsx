import { useCallback, useEffect, useState } from 'react';
import { getInvestmentPlan, saveAllocationPolicy } from '../api';
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

function useInvestmentPlan(owner: string) {
  const [state, setState] = useState<LoadState>({ kind: 'loading' });

  const load = useCallback(async () => {
    if (!owner) return;
    setState({ kind: 'loading' });
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

  useEffect(() => {
    void load(); // errors are captured into state inside load
  }, [load]);

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
  return (
    <table
      className="mb-3 w-full border-collapse text-sm"
      aria-label="Plan target"
    >
      <thead>
        <tr>
          <th className="px-2 py-1 text-left">Class</th>
          <th className="px-2 py-1 text-right">Target %</th>
          <th className="px-2 py-1 text-left">Vehicles</th>
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

function formatTargets(targets: Record<string, number>): string {
  const entries = Object.entries(targets);
  if (!entries.length) return 'none saved';
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

const PRIMARY_BUTTON =
  'mt-2 rounded bg-blue-500 px-3 py-1 text-white disabled:opacity-50';

/**
 * Plan vs rebalance targets. Right after an active plan is saved with a
 * different target (`offerSync`), asks whether to update the rebalance
 * targets; otherwise reports the mismatch with a copy button (#9680).
 */
function RebalanceComparison({
  owner,
  comparison,
  onCopied,
  offerSync,
  onDismiss,
}: {
  owner: string;
  comparison: Comparison;
  onCopied: () => Promise<void>;
  offerSync: boolean;
  onDismiss: () => void;
}) {
  const { copy, copying, error } = useCopyToRebalance(
    owner,
    comparison,
    onCopied
  );

  if (comparison.matches) {
    return (
      <p className="mb-3 text-sm text-green-700 dark:text-green-400">
        Your rebalance targets match this plan.
      </p>
    );
  }

  const prompt = offerSync && comparison.copy_supported;
  return (
    <div
      className="mb-3 text-sm"
      role="status"
      aria-label="Plan and rebalance mismatch"
    >
      <p className="text-amber-700 dark:text-amber-300">
        {prompt
          ? 'Update your rebalance targets to match this plan?'
          : 'Your rebalance targets differ from this plan.'}
      </p>
      <p>Plan: {formatTargets(comparison.plan_targets)}</p>
      <p>Rebalance targets: {formatTargets(comparison.rebalance_targets)}</p>
      {comparison.copy_supported ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void copy()}
            disabled={copying}
            className={PRIMARY_BUTTON}
          >
            {copying
              ? 'Updating…'
              : prompt
                ? 'Update rebalance targets'
                : 'Copy plan target to rebalance targets'}
          </button>
          {prompt && (
            <button
              type="button"
              onClick={onDismiss}
              className="mt-2 rounded bg-gray-200 px-3 py-1 text-slate-900"
            >
              Not now
            </button>
          )}
        </div>
      ) : (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Rebalance targets are set per asset class, so the plan is compared
          rolled up to that level.
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

function ratingText(rating: InvestmentPlanProfileRating | undefined): string {
  if (!rating) return 'not recorded';
  return rating.note ? `${rating.level} — ${rating.note}` : rating.level;
}

function yearsToGoalText(value: number | undefined): string {
  if (value == null) return '—';
  return value < 0 ? `${years.format(-value)} ago` : years.format(value);
}

function GoalTable({ data }: { data: InvestmentPlanResponse }) {
  const goals = data.plan.profile?.goals ?? [];
  if (!goals.length) return null;
  const toGo = new Map(
    (data.horizon?.goals ?? []).map((g) => [g.index, g.years_to_goal])
  );
  return (
    <table className="w-full border-collapse text-sm" aria-label="Plan goals">
      <thead>
        <tr>
          <th className="px-2 py-1 text-left">Goal</th>
          <th className="px-2 py-1 text-left">Purpose</th>
          <th className="px-2 py-1 text-left">Target date</th>
          <th className="px-2 py-1 text-right">Years to go</th>
          <th className="px-2 py-1 text-right">Amount</th>
          <th className="px-2 py-1 text-right">Priority</th>
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
              {yearsToGoalText(toGo.get(i))}
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
  const { profile } = data.plan;
  if (!profile) return null;
  const age = data.horizon?.age;
  return (
    <div className="mb-3" aria-label="Profile and goals" role="group">
      <h3 className="font-medium">Profile and goals</h3>
      <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">
        As you recorded them; not an assessment of suitability.
      </p>
      <ul className="mb-2 text-sm">
        {age != null && (
          <li>
            <span className="font-medium">Age:</span> {age}
          </li>
        )}
        <li>
          <span className="font-medium">Risk tolerance:</span>{' '}
          {ratingText(profile.risk_tolerance)}
        </li>
        <li>
          <span className="font-medium">Capacity for loss:</span>{' '}
          {ratingText(profile.capacity_for_loss)}
        </li>
      </ul>
      <GoalTable data={data} />
    </div>
  );
}

function PlanDetails({ plan }: { plan: InvestmentPlan }) {
  const assumptions = plan.assumptions.map(
    (a) =>
      `${a.key.replace(/_/g, ' ')}${a.value != null ? `: ${String(a.value)}` : ''}${a.note ? ` — ${a.note}` : ''}`
  );
  const decisions = plan.decisions.map(
    (d) => `${d.date}: ${d.decision}${d.reason ? ` (${d.reason})` : ''}`
  );
  const evidence = plan.evidence.map(
    (e) =>
      `${e.metric}: ${String(e.value)}${e.basis ? ` — ${e.basis}` : ''} (as of ${e.as_of}${e.source ? `, ${e.source}` : ''})`
  );
  return (
    <>
      <ListSection title="Key assumptions" items={assumptions} />
      <ListSection title="Open questions" items={plan.open_questions} />
      <details className="mb-3">
        <summary className="cursor-pointer font-medium">
          Decisions ({decisions.length}) and evidence ({evidence.length})
        </summary>
        <ListSection title="Decisions" items={decisions} />
        <ListSection title="Evidence" items={evidence} />
      </details>
      <p className="mb-1 text-sm">
        <span className="font-medium">Next review:</span>{' '}
        {plan.review.next_review ?? 'not set'}
      </p>
      <ListSection title="Review triggers" items={plan.review.triggers} />
    </>
  );
}

function PlanBody({
  owner,
  data,
  onCopied,
  offerSync,
  onDismissSync,
}: {
  owner: string;
  data: InvestmentPlanResponse;
  onCopied: () => Promise<void>;
  offerSync: boolean;
  onDismissSync: () => void;
}) {
  const { plan } = data;
  return (
    <>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {plan.status} · version {plan.version} · updated {plan.updated}
      </p>
      {plan.summary && <p className="mb-3">{plan.summary}</p>}
      <ProfileSection data={data} />
      {data.strategy && (
        <p className="mb-2 text-sm">
          <span className="font-medium">Matches strategy:</span>{' '}
          {data.strategy.name}
        </p>
      )}
      <TargetTable plan={plan} />
      <RebalanceComparison
        owner={owner}
        comparison={data.rebalance}
        onCopied={onCopied}
        offerSync={offerSync}
        onDismiss={onDismissSync}
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
}: {
  owner: string;
  onTargetsCopied?: () => Promise<void> | void;
}) {
  const { state, setState, load } = useInvestmentPlan(owner);
  const [editing, setEditing] = useState(false);
  // Set when an active plan was just saved with a target that differs from the rebalance targets.
  const [offerSync, setOfferSync] = useState(false);

  useEffect(() => {
    setEditing(false);
    setOfferSync(false);
  }, [owner]);

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
    <section className="mb-6 rounded border p-4" aria-label="Investment plan">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl">Investment plan</h2>
        {!editing && state.kind === 'ready' && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="rounded bg-gray-200 px-2 py-1 text-sm text-slate-900"
          >
            Edit plan
          </button>
        )}
      </div>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        Your own decisions, recorded with the reasoning behind them.
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
            <p className="text-sm text-slate-500">Loading plan…</p>
          )}
          {state.kind === 'error' && (
            <p className="break-words text-sm text-red-600">
              Unable to load the investment plan: {state.message}
            </p>
          )}
          {state.kind === 'missing' && (
            <EmptyState
              message={`No investment plan saved for ${owner} yet.`}
              actions={[
                { label: 'Create plan', onClick: () => setEditing(true) },
              ]}
            />
          )}
          {state.kind === 'ready' && (
            <PlanBody
              owner={owner}
              data={state.data}
              onCopied={handleCopied}
              offerSync={offerSync}
              onDismissSync={() => setOfferSync(false)}
            />
          )}
        </>
      )}
    </section>
  );
}
