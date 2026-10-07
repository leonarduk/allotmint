// Assign asset classes to the holdings the Strategy page reports as
// unclassified (#9495). The class is saved to the instrument metadata, which
// is where the rebalance plan reads it from.
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';
import { getRebalancePlan, setInstrumentAssetClass } from '../api';
import type { RebalancePlan, UnclassifiedHolding } from '../types';
import EmptyState from '../components/EmptyState';
import { useRoute } from '../RouteContext';
import { ASSET_CLASSES } from '../lib/allocationTargets';
import { assetClassLabel } from '../lib/assetClass';

const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
});

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

/** Unclassified holdings of the core plan and every sleeve, summed by ticker. */
function collectUnclassified(plan: RebalancePlan): UnclassifiedHolding[] {
  const byTicker = new Map<string, UnclassifiedHolding>();
  const plans = [plan, ...(plan.sleeves ?? []).map((s) => s.plan)];
  for (const p of plans) {
    for (const row of p?.unclassified_holdings ?? []) {
      const seen = byTicker.get(row.ticker);
      byTicker.set(
        row.ticker,
        seen ? { ...seen, value: seen.value + row.value } : { ...row }
      );
    }
  }
  return [...byTicker.values()].sort(
    (a, b) => b.value - a.value || a.ticker.localeCompare(b.ticker)
  );
}

function useUnclassified(owner: string) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<UnclassifiedHolding[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!owner) return;
    setError(null);
    try {
      setRows(collectUnclassified(await getRebalancePlan(owner)));
    } catch (err) {
      setRows(null);
      setError(t('classify.loadError', { owner, error: errorText(err) }));
    }
  }, [owner, t]);

  useEffect(() => {
    void reload(); // errors are captured into state inside reload
  }, [reload]);

  return { rows, error, reload };
}

function ClassifyRow({
  row,
  onSaved,
}: {
  row: UnclassifiedHolding;
  onSaved: (row: UnclassifiedHolding, assetClass: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [choice, setChoice] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectId = `classify-${row.ticker}`;

  const save = async () => {
    if (!row.exchange || !choice) return;
    setSaving(true);
    setError(null);
    try {
      await setInstrumentAssetClass(row.symbol, row.exchange, choice, row.name);
      await onSaved(row, choice);
    } catch (err) {
      setError(t('classify.saveError', { error: errorText(err) }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <tr>
      <td className="px-2 py-1">
        <Link
          to={`/research/${encodeURIComponent(row.ticker)}`}
          className="underline"
        >
          {row.ticker}
        </Link>
        {row.name && (
          <span className="ml-2 text-slate-600 dark:text-slate-300">
            {row.name}
          </span>
        )}
      </td>
      <td className="px-2 py-1 text-right">{gbp.format(row.value)}</td>
      <td className="px-2 py-1">
        {row.exchange ? (
          <div className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor={selectId}>
              {t('classify.selectLabel', { ticker: row.ticker })}
            </label>
            <select
              id={selectId}
              className="rounded border p-1"
              value={choice}
              onChange={(e) => setChoice(e.target.value)}
              disabled={saving}
            >
              <option value="">{t('classify.choose')}</option>
              {ASSET_CLASSES.map(({ key, label }) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="rounded border px-2 py-1"
              onClick={() => void save()}
              disabled={!choice || saving}
            >
              {saving ? t('classify.saving') : t('classify.save')}
            </button>
          </div>
        ) : (
          <span className="text-sm text-amber-700 dark:text-amber-300">
            {t('classify.noExchange')}
          </span>
        )}
        {error && (
          <p className="mt-1 break-words text-sm text-red-600">{error}</p>
        )}
      </td>
    </tr>
  );
}

export default function ClassifyHoldings() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const route = useRoute();
  const owner = params.get('owner')?.trim() || route.selectedOwner || '';
  const { rows, error, reload } = useUnclassified(owner);
  const [saved, setSaved] = useState<string | null>(null);

  const onSaved = useCallback(
    async (row: UnclassifiedHolding, assetClass: string) => {
      setSaved(
        t('classify.saved', {
          ticker: row.ticker,
          assetClass: assetClassLabel(assetClass),
        })
      );
      await reload();
    },
    [reload, t]
  );

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">{t('classify.title')}</h1>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
        {t('classify.intro')}
      </p>
      <p className="mb-4">
        <Link to="/strategy" className="underline">
          {t('classify.back')}
        </Link>
      </p>
      {!owner && <EmptyState message={t('classify.noOwner')} />}
      {error && (
        <p className="mb-4 break-words text-red-600 [overflow-wrap:anywhere]">
          {error}
        </p>
      )}
      {saved && (
        <p
          role="status"
          className="mb-4 text-sm text-green-700 dark:text-green-400"
        >
          {saved}
        </p>
      )}
      {rows && rows.length === 0 && (
        <EmptyState message={t('classify.empty')} />
      )}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="px-2 py-1 text-left">
                  {t('classify.col.holding')}
                </th>
                <th className="px-2 py-1 text-right">
                  {t('classify.col.value')}
                </th>
                <th className="px-2 py-1 text-left">
                  {t('classify.col.assetClass')}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <ClassifyRow key={row.ticker} row={row} onSaved={onSaved} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
