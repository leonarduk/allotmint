import { useCallback, useEffect, useState } from 'react';
import {
  getInvestmentPlan,
  saveAllocationPolicy,
  saveInvestmentPlan,
} from '../api';
import type {
  InvestmentPlan,
  InvestmentPlanResponse,
  InvestmentPlanVehicle,
} from '../types';
import EmptyState from './EmptyState';

/** Labels for plan class keys (backend PLAN_CLASS_PARENT) and parent asset classes. */
const CLASS_LABELS: Record<string, string> = {
  equity: 'Equity',
  small_cap_value: 'Small-cap value',
  long_gilts: 'Long gilts',
  intermediate_gilts: 'Intermediate gilts',
  short_gilts: 'Short gilts / ultrashort',
  index_linked: 'Index-linked',
  overseas_government: 'Overseas government',
  corporate_bonds: 'Corporate / credit',
  gold: 'Gold',
  commodities: 'Other commodities',
  cash: 'Cash',
  bond: 'Bond',
  commodity: 'Commodity',
  property: 'Property',
  'multi-asset': 'Multi-asset',
};

const classLabel = (key: string) => CLASS_LABELS[key] ?? key;

const pct = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 });

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

const errorStatus = (error: unknown): number | undefined =>
  (error as { status?: number } | null)?.status;

/** Starting point for a new plan in the JSON editor. */
function templatePlan(owner: string): Partial<InvestmentPlan> {
  return {
    owner,
    version: 1,
    updated: new Date().toISOString().slice(0, 10),
    status: 'draft',
    summary: '',
    target: [{ class: 'equity', weight_pct: 100 }],
    vehicles: {},
    assumptions: [],
    decisions: [],
    open_questions: [],
    evidence: [],
    review: { triggers: [] },
  };
}

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

function RebalanceComparison({
  owner,
  comparison,
  onCopied,
}: {
  owner: string;
  comparison: InvestmentPlanResponse['rebalance'];
  onCopied: () => Promise<void>;
}) {
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (comparison.matches) {
    return (
      <p className="mb-3 text-sm text-green-700 dark:text-green-400">
        Your rebalance targets match this plan.
      </p>
    );
  }

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

  return (
    <div
      className="mb-3 text-sm"
      role="status"
      aria-label="Plan and rebalance mismatch"
    >
      <p className="text-amber-700 dark:text-amber-300">
        Your rebalance targets differ from this plan.
      </p>
      <p>Plan: {formatTargets(comparison.plan_targets)}</p>
      <p>Rebalance targets: {formatTargets(comparison.rebalance_targets)}</p>
      {comparison.copy_supported ? (
        <button
          type="button"
          onClick={() => void copy()}
          disabled={copying}
          className="mt-2 rounded bg-blue-500 px-3 py-1 text-white disabled:opacity-50"
        >
          {copying ? 'Copying…' : 'Copy plan target to rebalance targets'}
        </button>
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

function PlanEditor({
  owner,
  initial,
  onSaved,
  onCancel,
}: {
  owner: string;
  initial: Partial<InvestmentPlan>;
  onSaved: (data: InvestmentPlanResponse) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(initial, null, 2));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    let parsed: Partial<InvestmentPlan>;
    try {
      parsed = JSON.parse(text) as Partial<InvestmentPlan>;
    } catch (err) {
      setError(`Invalid JSON: ${errorText(err)}`);
      return;
    }
    setSaving(true);
    try {
      onSaved(await saveInvestmentPlan(owner, parsed));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} aria-label="Edit investment plan">
      <textarea
        className="h-80 w-full border p-2 font-mono text-xs"
        value={text}
        onChange={(e) => setText(e.target.value)}
        aria-label="Plan JSON"
      />
      {error && (
        <p className="mt-1 break-words text-sm text-red-600">{error}</p>
      )}
      <div className="mt-2 flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-blue-500 px-4 py-1 text-white disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save plan'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded bg-gray-200 px-3 py-1 text-slate-900"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function PlanBody({
  owner,
  data,
  onCopied,
}: {
  owner: string;
  data: InvestmentPlanResponse;
  onCopied: () => Promise<void>;
}) {
  const { plan } = data;
  return (
    <>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {plan.status} · version {plan.version} · updated {plan.updated}
      </p>
      {plan.summary && <p className="mb-3">{plan.summary}</p>}
      <TargetTable plan={plan} />
      <RebalanceComparison
        owner={owner}
        comparison={data.rebalance}
        onCopied={onCopied}
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

  useEffect(() => setEditing(false), [owner]);

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
  const initial =
    state.kind === 'ready' ? state.data.plan : templatePlan(owner);

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
            <PlanBody owner={owner} data={state.data} onCopied={handleCopied} />
          )}
        </>
      )}
    </section>
  );
}
