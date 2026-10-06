import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Link } from 'react-router-dom';
import {
  getNewCashPlan,
  getOwners,
  getRebalancePlan,
  getStrategies,
  saveAllocationPolicy,
} from '../api';
import type {
  NewCashPlan,
  OwnerSummary,
  RebalanceAccount,
  RebalanceClassRow,
  RebalancePlan,
  RebalanceTrade,
  StrategyList,
} from '../types';
import EmptyState from '../components/EmptyState';
import StrategyLibrary from '../components/StrategyLibrary';
import TargetFields from '../components/TargetFields';
import { sanitizeOwners } from '../utils/owners';
import { useRoute } from '../RouteContext';
import {
  currentWeights,
  draftFromCurrent,
  draftFromTargets,
  draftTotalOk,
  targetsFromDraft,
  type TargetDraft,
} from '../lib/allocationTargets';
import { allocationKeyLabel, assetClassLabel } from '../lib/assetClass';

const pct = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
});

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

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
  const { t } = useTranslation();
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
      setError(t('strategy.loadPlanError', { owner, error: errorText(err) }));
    } finally {
      setLoading(false);
    }
  }, [owner, t]);

  useEffect(() => {
    void reload(); // errors are captured into state inside reload
  }, [reload]);

  return { plan, loading, error, reload };
}

function useStrategies(owner: string) {
  const { t } = useTranslation();
  const [data, setData] = useState<StrategyList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!owner) return;
    setError(null);
    try {
      setData(await getStrategies(owner));
    } catch (err) {
      setData(null);
      setError(
        t('strategy.loadStrategiesError', { owner, error: errorText(err) })
      );
    }
  }, [owner, t]);

  useEffect(() => {
    void reload(); // errors are captured into state inside reload
  }, [reload]);

  return { data, error, reload };
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
  const { t } = useTranslation();
  const [draft, setDraft] = useState<TargetDraft>(() =>
    draftFromTargets(plan.policy.targets)
  );
  const [tolerance, setTolerance] = useState(String(plan.policy.tolerance_pct));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = useMemo(() => currentWeights(plan), [plan]);

  useEffect(() => {
    setDraft(draftFromTargets(plan.policy.targets));
    setTolerance(String(plan.policy.tolerance_pct));
  }, [plan.policy]);

  const totalOk = draftTotalOk(draft);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await saveAllocationPolicy(owner, {
        targets: targetsFromDraft(draft),
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
    <form
      onSubmit={handleSave}
      className="mb-6"
      aria-label={t('strategy.targets.title')}
    >
      <h2 className="mb-2 text-xl">{t('strategy.targets.title')}</h2>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('strategy.targets.help')}
      </p>
      <TargetFields draft={draft} onChange={setDraft} current={current} />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <label className="text-sm" htmlFor="rebalance-tolerance">
          {t('strategy.targets.tolerance')}
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
          onClick={() => setDraft((d) => draftFromCurrent(plan, d.split))}
          className="rounded bg-gray-200 px-2 py-1 text-slate-900"
        >
          {t('strategy.targets.startFromCurrent')}
        </button>
        <button
          type="submit"
          disabled={!totalOk || saving}
          className="rounded bg-blue-500 px-4 py-2 text-white disabled:opacity-50"
        >
          {saving ? t('strategy.saving') : t('strategy.targets.save')}
        </button>
      </div>
      {error && (
        <p className="mt-2 break-words text-sm text-red-600">{error}</p>
      )}
    </form>
  );
}

function driftStatus(
  row: RebalanceClassRow,
  t: TFunction
): {
  text: string;
  className: string;
} {
  if (row.parent != null && row.parent === row.asset_class)
    return {
      text: t('strategy.drift.needsSubClass'),
      className: 'text-amber-600 dark:text-amber-400',
    };
  if (row.in_band == null || row.drift_pct == null)
    return { text: '—', className: '' };
  if (row.in_band)
    return {
      text: t('strategy.drift.inBand'),
      className: 'text-green-600 dark:text-green-400',
    };
  return row.drift_pct > 0
    ? {
        text: t('strategy.drift.overweight'),
        className: 'text-red-600 dark:text-red-400',
      }
    : {
        text: t('strategy.drift.underweight'),
        className: 'text-amber-600 dark:text-amber-400',
      };
}

/** "Bond › Long gilts" for sub-class rows; the backend label otherwise. */
function driftLabel(row: RebalanceClassRow): string {
  if (row.parent == null || row.parent === row.asset_class) return row.label;
  return `${assetClassLabel(row.parent)} › ${row.label}`;
}

function DriftTable({ plan }: { plan: RebalancePlan }) {
  const { t } = useTranslation();
  return (
    <section className="mb-6" aria-label={t('strategy.drift.ariaLabel')}>
      <h2 className="mb-2 text-xl">{t('strategy.drift.title')}</h2>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left">
                {t('strategy.drift.col.assetClass')}
              </th>
              <th className="px-2 py-1 text-right">
                {t('strategy.drift.col.value')}
              </th>
              <th className="px-2 py-1 text-right">
                {t('strategy.drift.col.current')}
              </th>
              <th className="px-2 py-1 text-right">
                {t('strategy.drift.col.target')}
              </th>
              <th className="px-2 py-1 text-right">
                {t('strategy.drift.col.driftPp')}
              </th>
              <th className="px-2 py-1 text-left">
                {t('strategy.drift.col.status')}
              </th>
            </tr>
          </thead>
          <tbody>
            {plan.classes.map((row) => {
              const status = driftStatus(row, t);
              return (
                <tr key={row.asset_class}>
                  <td className="px-2 py-1">{driftLabel(row)}</td>
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
                <td className="px-2 py-1">
                  {t('strategy.drift.unclassified')}
                </td>
                <td className="px-2 py-1 text-right">
                  {gbp.format(plan.unclassified_value)}
                </td>
                <td className="px-2 py-1 text-right">
                  {pct.format(plan.unclassified_pct)}%
                </td>
                <td className="px-2 py-1 text-right">—</td>
                <td className="px-2 py-1 text-right">—</td>
                <td className="px-2 py-1 text-amber-600 dark:text-amber-400">
                  {t('strategy.drift.needsAssetClass')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        {t('strategy.drift.totalLine', {
          total: gbp.format(plan.total_value),
          tolerance: pct.format(plan.policy.tolerance_pct),
        })}
      </p>
    </section>
  );
}

function SuggestedInstrument({ trade }: { trade: RebalanceTrade }) {
  const { t } = useTranslation();
  if (!trade.ticker) return <>{t('strategy.trades.chooseInstrument')}</>;
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
  const { t } = useTranslation();
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          <th className="px-2 py-1 text-left">
            {t('strategy.trades.col.action')}
          </th>
          <th className="px-2 py-1 text-left">
            {t('strategy.trades.col.assetClass')}
          </th>
          <th className="px-2 py-1 text-right">
            {t('strategy.trades.col.amount')}
          </th>
          <th className="px-2 py-1 text-left">
            {t('strategy.trades.col.suggested')}
          </th>
        </tr>
      </thead>
      <tbody>
        {trades.map((trade, index) => (
          <tr key={`${trade.action}-${trade.asset_class}-${index}`}>
            <td
              className={`px-2 py-1 ${trade.action === 'buy' ? 'text-green-600' : 'text-red-600'}`}
            >
              {trade.action.toUpperCase()}
            </td>
            <td className="px-2 py-1">
              {allocationKeyLabel(trade.asset_class)}
            </td>
            <td className="px-2 py-1 text-right">{gbp.format(trade.amount)}</td>
            <td className="px-2 py-1">
              <SuggestedInstrument trade={trade} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SuggestedTrades({ plan }: { plan: RebalancePlan }) {
  const { t } = useTranslation();
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
    <section className="mb-6" aria-label={t('strategy.trades.title')}>
      <h2 className="mb-2 text-xl">{t('strategy.trades.heading')}</h2>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('strategy.trades.help')}
      </p>
      {byAccount.length === 0 ? (
        <EmptyState message={t('strategy.trades.none')} />
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
  const { t } = useTranslation();
  const [amount, setAmount] = useState('');
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '');
  const [result, setResult] = useState<NewCashPlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Account ids are stable file stems (#9496), so a reloaded plan keeps the
  // selection. If the selected account is gone, fall back to the first one
  // rather than keep an id the select no longer shows and the API rejects.
  useEffect(() => {
    if (!accounts.some((a) => a.id === accountId)) {
      setAccountId(accounts[0]?.id ?? '');
    }
  }, [accounts, accountId]);

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
    <form
      onSubmit={handleSubmit}
      className="mb-6"
      aria-label={t('strategy.newCash.title')}
    >
      <h2 className="mb-2 text-xl">{t('strategy.newCash.title')}</h2>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('strategy.newCash.help')}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm" htmlFor="new-cash-amount">
          {t('strategy.newCash.amount')}
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
          {t('strategy.newCash.intoAccount')}
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
          {t('strategy.newCash.plan')}
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
              {t('strategy.newCash.keepAsCash', {
                amount: gbp.format(result.keep_as_cash),
              })}
            </p>
          )}
        </div>
      )}
    </form>
  );
}

export default function Strategy() {
  const { t } = useTranslation();
  const { owners, ownersError, selectedOwner, selectOwner } =
    useOwnerSelection();
  const { plan, loading, error, reload } = useRebalancePlan(selectedOwner);
  const strategies = useStrategies(selectedOwner);
  const reloadStrategies = strategies.reload;
  const hasPolicy = plan != null && Object.keys(plan.policy.targets).length > 0;
  const current = useMemo(() => (plan ? currentWeights(plan) : {}), [plan]);

  // Targets and the active strategy's "modified" flag change together.
  // The investment plan panel (PlanPanel) is hidden for now: it did not stay
  // in sync with the applied strategy. The /plans API and MCP tools remain.
  const reloadAll = useCallback(async () => {
    await Promise.all([reload(), reloadStrategies()]);
  }, [reload, reloadStrategies]);

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">{t('strategy.title')}</h1>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
        {t('strategy.intro')}
      </p>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium" htmlFor="rebalance-owner-select">
          {t('strategy.owner')}
        </label>
        <select
          id="rebalance-owner-select"
          className="rounded border p-1"
          value={selectedOwner}
          onChange={(e) => selectOwner(e.target.value)}
          disabled={owners.length === 0}
        >
          {owners.length === 0 && (
            <option value="">{t('strategy.noOwners')}</option>
          )}
          {owners.map((owner) => (
            <option key={owner.owner} value={owner.owner}>
              {owner.owner}
            </option>
          ))}
        </select>
        {loading && (
          <span className="text-xs text-slate-500">
            {t('strategy.loading')}
          </span>
        )}
      </div>
      {ownersError && (
        <p className="mb-4 break-words text-sm text-red-600">{ownersError}</p>
      )}
      {error && (
        <p className="mb-4 break-words text-red-600 [overflow-wrap:anywhere]">
          {error}
        </p>
      )}
      {strategies.error && (
        <p className="mb-4 break-words text-sm text-red-600">
          {strategies.error}
        </p>
      )}
      {strategies.data && (
        <StrategyLibrary
          owner={selectedOwner}
          data={strategies.data}
          current={current}
          hasTargets={hasPolicy}
          onChanged={reloadAll}
        />
      )}
      {plan && (
        <>
          <DriftTable plan={plan} />
          {plan.notes.length > 0 && (
            <ul
              className="mb-6 list-disc pl-5 text-sm text-amber-700 dark:text-amber-300"
              aria-label={t('strategy.notes')}
            >
              {plan.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
          <TargetEditor owner={selectedOwner} plan={plan} onSaved={reloadAll} />
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
            <EmptyState message={t('strategy.emptyPolicy')} />
          )}
        </>
      )}
    </div>
  );
}
