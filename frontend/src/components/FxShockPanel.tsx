import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { runFxScenario } from '../api';
import { money } from '../lib/money';
import type { FxScenarioResult } from '../types';

// Every /scenario/fx value is in GBP, and the shock itself is defined against
// GBP, so amounts are labelled GBP whatever the configured base currency:
// money() only changes the symbol, it does not convert (#9725).
const RESULT_CURRENCY = 'GBP';
const QUICK_CURRENCIES = ['USD', 'EUR', 'JPY', 'CHF'];
const STERLING = new Set(['GBP', 'GBX']);
const MIN_PCT = -100; // exclusive: a currency cannot lose more than all its value
const MAX_PCT = 1000;

const fmt = (v: number) => money(v, RESULT_CURRENCY);

/** Why ``currency``/``pct`` cannot be run, or null when they can (mirrors the API's checks). */
function inputError(currency: string, pct: number): string | null {
  if (!/^[A-Z]{3}$/.test(currency)) return 'invalidCurrency';
  if (STERLING.has(currency)) return 'sterling';
  if (!Number.isFinite(pct) || pct <= MIN_PCT || pct > MAX_PCT)
    return 'invalidPct';
  return null;
}

function FxResultsTable({
  currency,
  results,
}: {
  currency: string;
  results: FxScenarioResult[];
}) {
  const { t } = useTranslation();
  return (
    <table className="min-w-full border border-slate-200 text-sm">
      <thead className="bg-slate-50">
        <tr>
          <th className="p-2 text-left">{t('scenarioFx.owner')}</th>
          <th className="p-2 text-right">
            {t('scenarioFx.exposed', { currency })}
          </th>
          <th className="p-2 text-right">{t('scenarioFx.baseline')}</th>
          <th className="p-2 text-right">{t('scenarioFx.shocked')}</th>
          <th className="p-2 text-right">{t('scenarioFx.delta')}</th>
          <th className="p-2 text-right">{t('scenarioFx.impact')}</th>
        </tr>
      </thead>
      <tbody>
        {results.map((r) => (
          <tr key={r.owner} className="border-t">
            <td className="p-2 font-medium">{r.owner}</td>
            <td className="p-2 text-right">{fmt(r.exposed_value_gbp)}</td>
            <td className="p-2 text-right">
              {fmt(r.baseline_total_value_gbp)}
            </td>
            <td className="p-2 text-right">{fmt(r.shocked_total_value_gbp)}</td>
            <td className="p-2 text-right">{fmt(r.delta_gbp)}</td>
            <td className="p-2 text-right">
              {r.baseline_total_value_gbp
                ? `${((r.delta_gbp / r.baseline_total_value_gbp) * 100).toFixed(2)}%`
                : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FxResultNotes({ results }: { results: FxScenarioResult[] }) {
  const { t } = useTranslation();
  const unconverted = results.flatMap((r) => r.unconverted_holdings);
  const skipped = results.reduce((n, r) => n + r.skipped_unknown_currency, 0);
  return (
    <div className="mt-2 flex flex-col gap-1 text-xs text-slate-500">
      {unconverted.length > 0 && (
        <p className="text-amber-700">
          {t('scenarioFx.unconverted', {
            holdings: unconverted
              .map((h) => `${h.ticker} (${h.currency})`)
              .join(', '),
          })}
        </p>
      )}
      {skipped > 0 && (
        <p>{t('scenarioFx.skippedUnknown', { count: skipped })}</p>
      )}
    </div>
  );
}

function FxShockForm({
  currency,
  pct,
  onCurrency,
  onPct,
}: {
  currency: string;
  pct: string;
  onCurrency: (value: string) => void;
  onPct: (value: string) => void;
}) {
  const { t } = useTranslation();
  const code = currency || 'XXX';
  return (
    <div className="flex flex-col gap-2 md:flex-row md:items-end">
      <label className="flex flex-col gap-1 text-sm">
        <span>{t('scenarioFx.currency')}</span>
        <input
          type="text"
          value={currency}
          maxLength={3}
          onChange={(e) => onCurrency(e.target.value.toUpperCase())}
          className="w-24 rounded border border-slate-300 px-2 py-1 uppercase"
        />
      </label>
      <div className="flex flex-wrap gap-1">
        {QUICK_CURRENCIES.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => onCurrency(c)}
            aria-pressed={currency === c}
            className={`rounded px-2 py-1 text-xs ${
              currency === c
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            {c}
          </button>
        ))}
      </div>
      <label className="flex flex-col gap-1 text-sm">
        <span>{t('scenarioFx.pctLabel', { currency: code })}</span>
        <input
          type="number"
          value={pct}
          step={1}
          onChange={(e) => onPct(e.target.value)}
          className="w-28 rounded border border-slate-300 px-2 py-1 text-right"
        />
      </label>
    </div>
  );
}

/** Currency shock: revalue every portfolio for one currency moving against GBP (#9725). */
export function FxShockPanel() {
  const { t } = useTranslation();
  const [currency, setCurrency] = useState('USD');
  const [pct, setPct] = useState('-10');
  // The currency is kept with the results so editing the form does not relabel them.
  const [run, setRun] = useState<{
    currency: string;
    results: FxScenarioResult[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pctValue = pct.trim() === '' ? Number.NaN : Number(pct);
  const invalid = inputError(currency, pctValue);

  async function handleRun() {
    setError(null);
    try {
      setRun({
        currency,
        results: await runFxScenario({ currency, pct: pctValue }),
      });
    } catch (e) {
      setRun(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="rounded-md border border-slate-200 bg-white p-4 text-slate-900 shadow-sm">
      <h2 className="mb-3 text-lg font-semibold">{t('scenarioFx.title')}</h2>
      <p className="mb-4 text-sm text-slate-600">
        {t('scenarioFx.description')}
      </p>
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-end md:gap-4">
        <FxShockForm
          currency={currency}
          pct={pct}
          onCurrency={setCurrency}
          onPct={setPct}
        />
        <button
          type="button"
          onClick={handleRun}
          disabled={invalid !== null}
          className="w-fit rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {t('scenarioFx.run')}
        </button>
      </div>
      {invalid && currency !== '' && (
        <p className="mb-3 text-sm text-slate-500">
          {t(`scenarioFx.errors.${invalid}`)}
        </p>
      )}
      <p className="mb-3 text-xs text-slate-500">
        {t('scenarioFx.signConvention', { currency: currency || 'XXX' })}
      </p>
      {error && <div className="mb-3 text-sm text-red-500">{error}</div>}
      {run && (
        <div className="overflow-auto">
          <FxResultsTable currency={run.currency} results={run.results} />
          <FxResultNotes results={run.results} />
        </div>
      )}
    </section>
  );
}

export default FxShockPanel;
