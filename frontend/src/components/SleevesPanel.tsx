// Sleeves for the strategy page (#9813): split the portfolio into a core and
// other sleeves (e.g. 10% speculative), each with its own strategy, and tag
// holdings into them. The core is sized by the rest and targeted by the
// owner's allocation policy (the library's Apply), so it is not edited here.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  applyStrategyToSleeve,
  assignSleeve,
  createSleeve,
  deleteSleeve,
  getSleeves,
  updateSleeve,
} from '../api';
import type {
  RebalanceSleeveRow,
  Sleeve,
  SleeveList,
  Strategy,
} from '../types';
import { formatStrategyTargets } from '../lib/allocationTargets';

const CORE_ID = 'core';

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

function useSleeves(owner: string) {
  const { t } = useTranslation();
  const [data, setData] = useState<SleeveList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!owner) return;
    setError(null);
    try {
      setData(await getSleeves(owner));
    } catch (err) {
      setData(null);
      setError(t('sleeves.loadError', { owner, error: errorText(err) }));
    }
  }, [owner, t]);

  useEffect(() => {
    void reload(); // errors are captured into state inside reload
  }, [reload]);

  return { data, error, reload };
}

function StrategySelect({
  id,
  strategies,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  strategies: Strategy[];
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <select
      id={id}
      className="rounded border p-1"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{placeholder}</option>
      {strategies.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  );
}

function SizeCell({ row }: { row?: RebalanceSleeveRow }) {
  const { t } = useTranslation();
  if (!row) return <>—</>;
  const drift = `${row.size_drift_pct > 0 ? '+' : ''}${pct.format(row.size_drift_pct)}`;
  const tone =
    row.in_band === false
      ? 'text-red-600 dark:text-red-400'
      : 'text-green-600 dark:text-green-400';
  return (
    <>
      {pct.format(row.size_current_pct)}% ({gbp.format(row.current_value)}){' '}
      <span className={tone}>{t('sleeves.driftPp', { drift })}</span>
    </>
  );
}

function SleeveRow({
  owner,
  sleeve,
  current,
  strategies,
  onChanged,
}: {
  owner: string;
  sleeve: Sleeve;
  current?: RebalanceSleeveRow;
  strategies: Strategy[];
  onChanged: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const isCore = sleeve.id === CORE_ID;
  const [size, setSize] = useState(String(sleeve.size_pct));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setSize(String(sleeve.size_pct)), [sleeve.size_pct]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await onChanged();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const targets = formatStrategyTargets(sleeve.targets);
  return (
    <tr className="align-top">
      <td className="px-2 py-1 font-medium">
        {isCore ? t('sleeves.core') : sleeve.name}
      </td>
      <td className="px-2 py-1 text-right">
        {isCore ? (
          `${pct.format(sleeve.size_pct)}%`
        ) : (
          <span className="inline-flex items-center gap-1">
            <input
              type="number"
              step="any"
              min="0"
              max="100"
              aria-label={t('sleeves.sizeFor', { name: sleeve.name })}
              className="w-20 border p-1 text-right"
              value={size}
              onChange={(e) => setSize(e.target.value)}
            />
            %
            {parseFloat(size) !== sleeve.size_pct && (
              <button
                type="button"
                disabled={busy || !(parseFloat(size) > 0)}
                className="rounded bg-blue-500 px-2 py-1 text-xs text-white disabled:opacity-50"
                onClick={() =>
                  run(() =>
                    updateSleeve(owner, sleeve.id, {
                      size_pct: parseFloat(size),
                    })
                  )
                }
              >
                {t('sleeves.saveSize')}
              </button>
            )}
          </span>
        )}
      </td>
      <td className="px-2 py-1 text-right">
        <SizeCell row={current} />
      </td>
      <td className="px-2 py-1">
        <div>
          {sleeve.strategy?.name ??
            (targets ? t('sleeves.customTargets') : t('sleeves.noTargets'))}
        </div>
        {targets && (
          <div className="text-xs text-slate-500 dark:text-slate-400">
            {targets}
          </div>
        )}
        {isCore && (
          <div className="text-xs text-slate-500 dark:text-slate-400">
            {t('sleeves.coreHelp')}
          </div>
        )}
        {error && (
          <div className="break-words text-xs text-red-600">{error}</div>
        )}
      </td>
      <td className="px-2 py-1">
        {!isCore && (
          <div className="flex flex-wrap items-center gap-2">
            <StrategySelect
              id={`sleeve-apply-${sleeve.id}`}
              strategies={strategies}
              value=""
              placeholder={t('sleeves.applyStrategy')}
              onChange={(strategyId) =>
                strategyId &&
                run(() => applyStrategyToSleeve(owner, sleeve.id, strategyId))
              }
            />
            <button
              type="button"
              disabled={busy}
              className="rounded bg-red-600 px-2 py-1 text-xs text-white disabled:opacity-50"
              onClick={() => {
                if (
                  window.confirm(
                    t('sleeves.confirmDelete', { name: sleeve.name })
                  )
                )
                  void run(() => deleteSleeve(owner, sleeve.id));
              }}
            >
              {t('sleeves.delete')}
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}

function AddSleeveForm({
  owner,
  strategies,
  onChanged,
}: {
  owner: string;
  strategies: Strategy[];
  onChanged: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [size, setSize] = useState('');
  const [strategyId, setStrategyId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createSleeve(owner, {
        name: name.trim(),
        size_pct: parseFloat(size),
        strategy_id: strategyId,
      });
      setName('');
      setSize('');
      setStrategyId('');
      await onChanged();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-3 flex flex-wrap items-center gap-2"
      aria-label={t('sleeves.add.title')}
    >
      <label className="text-sm" htmlFor="sleeve-name">
        {t('sleeves.add.name')}
      </label>
      <input
        id="sleeve-name"
        className="w-40 border p-1"
        value={name}
        placeholder={t('sleeves.add.namePlaceholder')}
        onChange={(e) => setName(e.target.value)}
      />
      <label className="text-sm" htmlFor="sleeve-size">
        {t('sleeves.add.size')}
      </label>
      <input
        id="sleeve-size"
        type="number"
        step="any"
        min="0"
        max="100"
        className="w-20 border p-1"
        value={size}
        onChange={(e) => setSize(e.target.value)}
      />
      <label className="text-sm" htmlFor="sleeve-strategy">
        {t('sleeves.add.strategy')}
      </label>
      <StrategySelect
        id="sleeve-strategy"
        strategies={strategies}
        value={strategyId}
        placeholder={t('sleeves.add.chooseStrategy')}
        onChange={setStrategyId}
      />
      <button
        type="submit"
        disabled={
          saving || !name.trim() || !(parseFloat(size) > 0) || !strategyId
        }
        className="rounded bg-blue-500 px-3 py-1 text-white disabled:opacity-50"
      >
        {t('sleeves.add.submit')}
      </button>
      {error && (
        <p className="w-full break-words text-sm text-red-600">{error}</p>
      )}
    </form>
  );
}

function HoldingAssignments({
  owner,
  data,
  onChanged,
}: {
  owner: string;
  data: SleeveList;
  onChanged: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const holdings = data.holdings ?? [];
  if (holdings.length === 0) return null;

  async function assign(ticker: string, sleeveId: string) {
    setError(null);
    try {
      await assignSleeve(owner, ticker, sleeveId === CORE_ID ? null : sleeveId);
      await onChanged();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <details className="mt-4">
      <summary className="cursor-pointer text-sm font-medium">
        {t('sleeves.assign.title')}
      </summary>
      <p className="my-2 text-xs text-slate-500 dark:text-slate-400">
        {t('sleeves.assign.help')}
      </p>
      {error && <p className="break-words text-sm text-red-600">{error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left">
                {t('sleeves.assign.col.holding')}
              </th>
              <th className="px-2 py-1 text-right">
                {t('sleeves.assign.col.value')}
              </th>
              <th className="px-2 py-1 text-left">
                {t('sleeves.assign.col.sleeve')}
              </th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => (
              <tr key={h.ticker}>
                <td className="px-2 py-1">
                  {h.name ? `${h.name} (${h.ticker})` : h.ticker}
                </td>
                <td className="px-2 py-1 text-right">{gbp.format(h.value)}</td>
                <td className="px-2 py-1">
                  <select
                    className="rounded border p-1"
                    aria-label={t('sleeves.assign.sleeveFor', {
                      ticker: h.ticker,
                    })}
                    value={h.sleeve_id}
                    onChange={(e) => void assign(h.ticker, e.target.value)}
                  >
                    {data.sleeves.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.id === CORE_ID ? t('sleeves.core') : s.name}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export default function SleevesPanel({
  owner,
  strategies,
  planSleeves,
  onChanged,
}: {
  owner: string;
  strategies: Strategy[];
  /** Size drift from the rebalance plan, when the owner has sleeves. */
  planSleeves?: RebalanceSleeveRow[];
  /** Reload the plan and strategies after any sleeve change. */
  onChanged: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const { data, error, reload } = useSleeves(owner);
  const currentById = useMemo(
    () => new Map((planSleeves ?? []).map((row) => [row.id, row])),
    [planSleeves]
  );

  const changed = useCallback(async () => {
    await Promise.all([reload(), onChanged()]);
  }, [reload, onChanged]);

  return (
    <section className="mb-6" aria-label={t('sleeves.title')}>
      <h2 className="mb-2 text-xl">{t('sleeves.title')}</h2>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('sleeves.help')}
      </p>
      {error && <p className="break-words text-sm text-red-600">{error}</p>}
      {data?.warnings?.map((warning) => (
        <p
          key={warning}
          role="alert"
          className="mb-2 break-words text-sm text-amber-700 dark:text-amber-300"
        >
          {warning}
        </p>
      ))}
      {data && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left">
                    {t('sleeves.col.sleeve')}
                  </th>
                  <th className="px-2 py-1 text-right">
                    {t('sleeves.col.target')}
                  </th>
                  <th className="px-2 py-1 text-right">
                    {t('sleeves.col.current')}
                  </th>
                  <th className="px-2 py-1 text-left">
                    {t('sleeves.col.strategy')}
                  </th>
                  <th className="px-2 py-1 text-left">
                    {t('sleeves.col.actions')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.sleeves.map((sleeve) => (
                  <SleeveRow
                    key={sleeve.id}
                    owner={owner}
                    sleeve={sleeve}
                    current={currentById.get(sleeve.id)}
                    strategies={strategies}
                    onChanged={changed}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <AddSleeveForm
            owner={owner}
            strategies={strategies}
            onChanged={changed}
          />
          {data.sleeves.length > 1 && (
            <HoldingAssignments owner={owner} data={data} onChanged={changed} />
          )}
        </>
      )}
    </section>
  );
}
