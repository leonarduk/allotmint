import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  getNewCashPlan,
  getOwners,
  getRebalancePlan,
  saveAllocationPolicy,
} from '../api';
import type {
  NewCashPlan,
  OwnerSummary,
  RebalanceAccount,
  RebalanceClassRow,
  RebalancePlan,
  RebalanceTrade,
} from '../types';
import EmptyState from '../components/EmptyState';
import PlanPanel from '../components/PlanPanel';
import { sanitizeOwners } from '../utils/owners';
import { useRoute } from '../RouteContext';

/** Canonical asset classes, matching backend ASSET_CLASSES / ASSET_CLASS_LABELS. */
const ASSET_CLASSES: Array<{ key: string; label: string }> = [
  { key: 'equity', label: 'Equity' },
  { key: 'bond', label: 'Bond' },
  { key: 'cash', label: 'Cash' },
  { key: 'commodity', label: 'Commodity' },
  { key: 'property', label: 'Property' },
  { key: 'multi-asset', label: 'Multi-asset' },
];
const LABELS = Object.fromEntries(ASSET_CLASSES.map((c) => [c.key, c.label]));

const pct = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
});

type DraftTargets = Record<string, string>;

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

function draftFromTargets(targets: Record<string, number>): DraftTargets {
  return Object.fromEntries(
    ASSET_CLASSES.map(({ key }) => [
      key,
      targets[key] != null ? String(targets[key]) : '',
    ])
  );
}

function sumDraft(draft: DraftTargets): number {
  return Object.values(draft).reduce((sum, value) => {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? sum + parsed : sum;
  }, 0);
}

function useOwnerSelection() {
  const route = useRoute();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [ownersError, setOwnersError] = useState<string | null>(null);
  const [selectedOwner, setSelectedOwner] = useState('');

  useEffect(() => {
    let cancelled = false;
    getOwners()
      .then((list) => {
        if (!cancelled)
          setOwners(sanitizeOwners(Array.isArray(list) ? list : []));
      })
      .catch((error) => {
        if (!cancelled) setOwnersError(errorText(error));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!owners.length) return;
    const routeOwner = route.selectedOwner?.trim();
    const preferred =
      routeOwner && owners.some((o) => o.owner === routeOwner)
        ? routeOwner
        : owners[0].owner;
    setSelectedOwner((current) => current || preferred);
  }, [owners, route.selectedOwner]);

  const selectOwner = (owner: string) => {
    setSelectedOwner(owner);
    route.setSelectedOwner(owner);
  };
  return { owners, ownersError, selectedOwner, selectOwner };
}

function useRebalancePlan(owner: string) {
  const [plan, setPlan] = useState<RebalancePlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!owner) return;
    setLoading(true);
    setError(null);
    try {
      setPlan(await getRebalancePlan(owner));
    } catch (err) {
      setPlan(null);
      setError(`Unable to load rebalance plan for ${owner}: ${errorText(err)}`);
    } finally {
      setLoading(false);
    }
  }, [owner]);

  useEffect(() => {
    void reload(); // errors are captured into state inside reload
  }, [reload]);

  return { plan, loading, error, reload };
}

function TargetEditor({
  owner,
  plan,
  onSaved,
}: {
  owner: string;
  plan: RebalancePlan;
  onSaved: () => Promise<void>;
}) {
  const [draft, setDraft] = useState<DraftTargets>(() =>
    draftFromTargets(plan.policy.targets)
  );
  const [tolerance, setTolerance] = useState(String(plan.policy.tolerance_pct));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(draftFromTargets(plan.policy.targets));
    setTolerance(String(plan.policy.tolerance_pct));
  }, [plan.policy]);

  const total = sumDraft(draft);
  const totalOk = Math.abs(total - 100) <= 0.01;

  const useCurrent = () => {
    const current = Object.fromEntries(
      plan.classes.map((row) => [row.asset_class, row.current_pct])
    );
    setDraft(draftFromTargets(current));
  };

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    const targets: Record<string, number> = {};
    for (const [key, value] of Object.entries(draft)) {
      const parsed = parseFloat(value);
      if (Number.isFinite(parsed) && parsed > 0) targets[key] = parsed;
    }
    setSaving(true);
    setError(null);
    try {
      await saveAllocationPolicy(owner, {
        targets,
        tolerance_pct: parseFloat(tolerance),
      });
      await onSaved();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="mb-6" aria-label="Target allocation">
      <h2 className="mb-2 text-xl">Target allocation</h2>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        Set the share of your whole portfolio each asset class should be. Trades
        are only suggested for classes that drift further than the tolerance
        band.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left">Asset class</th>
              <th className="px-2 py-1 text-left">Target %</th>
            </tr>
          </thead>
          <tbody>
            {ASSET_CLASSES.map(({ key, label }) => (
              <tr key={key}>
                <td className="px-2 py-1">{label}</td>
                <td className="px-2 py-1">
                  <input
                    type="number"
                    step="any"
                    min="0"
                    max="100"
                    className="w-full border p-1"
                    value={draft[key] ?? ''}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, [key]: e.target.value }))
                    }
                    aria-label={`Target % for ${label}`}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p
        className={`mt-2 text-xs ${totalOk ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
      >
        Total: {pct.format(total)}% {totalOk ? '' : '(must equal 100%)'}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <label className="text-sm" htmlFor="rebalance-tolerance">
          Tolerance band (± percentage points)
        </label>
        <input
          id="rebalance-tolerance"
          type="number"
          step="any"
          min="0"
          max="50"
          className="w-24 border p-1"
          value={tolerance}
          onChange={(e) => setTolerance(e.target.value)}
        />
        <button
          type="button"
          onClick={useCurrent}
          className="rounded bg-gray-200 px-2 py-1 text-slate-900"
        >
          Start from current allocation
        </button>
        <button
          type="submit"
          disabled={!totalOk || saving}
          className="rounded bg-blue-500 px-4 py-2 text-white disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save targets'}
        </button>
      </div>
      {error && (
        <p className="mt-2 break-words text-sm text-red-600">{error}</p>
      )}
    </form>
  );
}

function driftStatus(row: RebalanceClassRow): {
  text: string;
  className: string;
} {
  if (row.in_band == null || row.drift_pct == null)
    return { text: '—', className: '' };
  if (row.in_band)
    return { text: 'In band', className: 'text-green-600 dark:text-green-400' };
  return row.drift_pct > 0
    ? { text: 'Overweight', className: 'text-red-600 dark:text-red-400' }
    : { text: 'Underweight', className: 'text-amber-600 dark:text-amber-400' };
}

function DriftTable({ plan }: { plan: RebalancePlan }) {
  return (
    <section className="mb-6" aria-label="Allocation drift">
      <h2 className="mb-2 text-xl">Drift</h2>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left">Asset class</th>
              <th className="px-2 py-1 text-right">Value</th>
              <th className="px-2 py-1 text-right">Current %</th>
              <th className="px-2 py-1 text-right">Target %</th>
              <th className="px-2 py-1 text-right">Drift (pp)</th>
              <th className="px-2 py-1 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {plan.classes.map((row) => {
              const status = driftStatus(row);
              return (
                <tr key={row.asset_class}>
                  <td className="px-2 py-1">{row.label}</td>
                  <td className="px-2 py-1 text-right">
                    {gbp.format(row.current_value)}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {pct.format(row.current_pct)}%
                  </td>
                  <td className="px-2 py-1 text-right">
                    {row.target_pct == null
                      ? '—'
                      : `${pct.format(row.target_pct)}%`}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {row.drift_pct == null
                      ? '—'
                      : `${row.drift_pct > 0 ? '+' : ''}${pct.format(row.drift_pct)}`}
                  </td>
                  <td className={`px-2 py-1 ${status.className}`}>
                    {status.text}
                  </td>
                </tr>
              );
            })}
            {plan.unclassified_value > 0 && (
              <tr>
                <td className="px-2 py-1">Unclassified</td>
                <td className="px-2 py-1 text-right">
                  {gbp.format(plan.unclassified_value)}
                </td>
                <td className="px-2 py-1 text-right">
                  {pct.format(plan.unclassified_pct)}%
                </td>
                <td className="px-2 py-1 text-right">—</td>
                <td className="px-2 py-1 text-right">—</td>
                <td className="px-2 py-1 text-amber-600 dark:text-amber-400">
                  Needs an asset class
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Total {gbp.format(plan.total_value)} · tolerance ±
        {pct.format(plan.policy.tolerance_pct)} pp
      </p>
    </section>
  );
}

function SuggestedInstrument({ trade }: { trade: RebalanceTrade }) {
  if (!trade.ticker) return <>Choose an instrument</>;
  return (
    <Link
      to={`/research/${encodeURIComponent(trade.ticker)}`}
      className="underline"
    >
      {trade.name ? (
        <>
          {trade.name}{' '}
          <span className="text-slate-500 dark:text-slate-400">
            ({trade.ticker})
          </span>
        </>
      ) : (
        trade.ticker
      )}
    </Link>
  );
}

function TradeTable({ trades }: { trades: RebalanceTrade[] }) {
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          <th className="px-2 py-1 text-left">Action</th>
          <th className="px-2 py-1 text-left">Asset class</th>
          <th className="px-2 py-1 text-right">Amount</th>
          <th className="px-2 py-1 text-left">Suggested instrument</th>
        </tr>
      </thead>
      <tbody>
        {trades.map((t, index) => (
          <tr key={`${t.action}-${t.asset_class}-${index}`}>
            <td
              className={`px-2 py-1 ${t.action === 'buy' ? 'text-green-600' : 'text-red-600'}`}
            >
              {t.action.toUpperCase()}
            </td>
            <td className="px-2 py-1">
              {LABELS[t.asset_class] ?? t.asset_class}
            </td>
            <td className="px-2 py-1 text-right">{gbp.format(t.amount)}</td>
            <td className="px-2 py-1">
              <SuggestedInstrument trade={t} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SuggestedTrades({ plan }: { plan: RebalancePlan }) {
  const byAccount = useMemo(() => {
    const groups = new Map<
      string,
      { label: string; trades: RebalanceTrade[] }
    >();
    for (const trade of plan.trades) {
      const group = groups.get(trade.account_id) ?? {
        label: trade.account,
        trades: [],
      };
      group.trades.push(trade);
      groups.set(trade.account_id, group);
    }
    return [...groups.entries()];
  }, [plan.trades]);

  return (
    <section className="mb-6" aria-label="Suggested trades">
      <h2 className="mb-2 text-xl">Suggested trades</h2>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        Trades stay inside each account: buys are funded only by that
        account&apos;s sales and its cash above your cash target. Nothing moves
        between accounts.
      </p>
      {byAccount.length === 0 ? (
        <EmptyState message="No trades required — every asset class is within its band." />
      ) : (
        byAccount.map(([id, group]) => (
          <div key={id} className="mb-4 overflow-x-auto">
            <h3 className="mb-1 font-medium">{group.label}</h3>
            <TradeTable trades={group.trades} />
          </div>
        ))
      )}
    </section>
  );
}

function NewCashPlanner({
  owner,
  accounts,
}: {
  owner: string;
  accounts: RebalanceAccount[];
}) {
  const [amount, setAmount] = useState('');
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '');
  const [result, setResult] = useState<NewCashPlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setResult(await getNewCashPlan(owner, parseFloat(amount), accountId));
    } catch (err) {
      setResult(null);
      setError(errorText(err));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mb-6" aria-label="Invest new cash">
      <h2 className="mb-2 text-xl">Invest new cash</h2>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        Plan a contribution without selling anything: the money goes to the most
        underweight classes first.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm" htmlFor="new-cash-amount">
          Amount (£)
        </label>
        <input
          id="new-cash-amount"
          type="number"
          step="any"
          min="0"
          className="w-32 border p-1"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <label className="text-sm" htmlFor="new-cash-account">
          Into account
        </label>
        <select
          id="new-cash-account"
          className="rounded border p-1"
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={!(parseFloat(amount) > 0) || !accountId}
          className="rounded bg-blue-500 px-4 py-2 text-white disabled:opacity-50"
        >
          Plan contribution
        </button>
      </div>
      {error && (
        <p className="mt-2 break-words text-sm text-red-600">{error}</p>
      )}
      {result && (
        <div className="mt-3 overflow-x-auto">
          {result.trades.length > 0 && <TradeTable trades={result.trades} />}
          {result.keep_as_cash > 0 && (
            <p className="mt-1 text-sm">
              Keep {gbp.format(result.keep_as_cash)} as cash.
            </p>
          )}
        </div>
      )}
    </form>
  );
}

export default function Rebalance() {
  const { owners, ownersError, selectedOwner, selectOwner } =
    useOwnerSelection();
  const { plan, loading, error, reload } = useRebalancePlan(selectedOwner);
  const hasPolicy = plan != null && Object.keys(plan.policy.targets).length > 0;

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">Rebalance Portfolio</h1>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
        Compare your allocation by asset class against the targets you set, and
        see which trades — or which contribution — would bring it back within
        your tolerance band.
      </p>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium" htmlFor="rebalance-owner-select">
          Portfolio owner
        </label>
        <select
          id="rebalance-owner-select"
          className="rounded border p-1"
          value={selectedOwner}
          onChange={(e) => selectOwner(e.target.value)}
          disabled={owners.length === 0}
        >
          {owners.length === 0 && <option value="">No owners</option>}
          {owners.map((owner) => (
            <option key={owner.owner} value={owner.owner}>
              {owner.owner}
            </option>
          ))}
        </select>
        {loading && <span className="text-xs text-slate-500">Loading…</span>}
      </div>
      {ownersError && (
        <p className="mb-4 break-words text-sm text-red-600">{ownersError}</p>
      )}
      {error && (
        <p className="mb-4 break-words text-red-600 [overflow-wrap:anywhere]">
          {error}
        </p>
      )}
      <PlanPanel owner={selectedOwner} onTargetsCopied={reload} />
      {plan && (
        <>
          <DriftTable plan={plan} />
          {plan.notes.length > 0 && (
            <ul
              className="mb-6 list-disc pl-5 text-sm text-amber-700 dark:text-amber-300"
              aria-label="Notes"
            >
              {plan.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
          <TargetEditor owner={selectedOwner} plan={plan} onSaved={reload} />
          {hasPolicy ? (
            <>
              <SuggestedTrades plan={plan} />
              <NewCashPlanner
                key={selectedOwner}
                owner={selectedOwner}
                accounts={plan.accounts}
              />
            </>
          ) : (
            <EmptyState message="Save target allocations to see drift status and suggested trades." />
          )}
        </>
      )}
    </div>
  );
}
