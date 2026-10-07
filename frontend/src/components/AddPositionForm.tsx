import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { createManualHolding } from '../api';
import type { ManualHoldingPayload, ManualHoldingResult } from '../api';
import { useDemoReadOnly } from '../hooks/useDemoReadOnly';

type AmountMode = 'unitsPrice' | 'value';

type Props = {
  owner: string;
  accounts: string[];
  defaultAccount?: string;
  onAdded?: () => void;
  onCollapse?: () => void;
  controlsId?: string;
};

type FormValues = {
  owner: string;
  account: string;
  ticker: string;
  mode: AmountMode;
  units: string;
  price: string;
  value: string;
  date: string;
  openingBalance: boolean;
};

/** A preview is only valid for the exact inputs it was computed from. */
type Preview = { key: string; result: ManualHoldingResult };

/** Today's date in the user's local time zone, as YYYY-MM-DD. */
const todayIso = () => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

const inputClass =
  'mt-1 w-full rounded border border-gray-700 bg-gray-800 p-2 text-white';

/** The payload for ``values``, or a translated validation error. */
function buildPayload(
  values: FormValues,
  t: TFunction
): ManualHoldingPayload | string {
  const ticker = values.ticker.trim().toUpperCase();
  if (!ticker) return t('addPosition.errors.tickerRequired');
  if (!values.account) return t('addPosition.errors.accountRequired');
  // Omitting the date asks the backend for an opening balance (dated at the
  // account's first transaction); otherwise the change is dated as chosen.
  const base = {
    owner: values.owner,
    account: values.account,
    ticker,
    ...(values.openingBalance ? {} : { date: values.date || todayIso() }),
  };
  if (values.mode === 'value') {
    const valueGbp = Number(values.value);
    if (!Number.isFinite(valueGbp) || valueGbp <= 0)
      return t('addPosition.errors.positiveNumber');
    return { ...base, value_gbp: valueGbp };
  }
  if (values.units.trim() === '' || values.price.trim() === '')
    return t('addPosition.errors.amountRequired');
  const units = Number(values.units);
  const price = Number(values.price);
  if (
    !Number.isFinite(units) ||
    units <= 0 ||
    !Number.isFinite(price) ||
    price <= 0
  ) {
    return t('addPosition.errors.positiveNumber');
  }
  return { ...base, units, price_gbp: price };
}

function PreviewSummary({ result }: { result: ManualHoldingResult }) {
  const { t } = useTranslation();
  const tx = result.transaction;
  const target = Number(result.holding.units ?? 0);
  return (
    <div className="mt-3 space-y-1 text-sm" data-testid="add-position-preview">
      <p className="text-gray-200">
        {tx
          ? t('addPosition.preview.change', {
              sign: tx.type === 'TRANSFER_OUT' ? '-' : '+',
              units: tx.units,
              ticker: tx.ticker,
              type: tx.type,
              date: tx.date,
              price: tx.price_gbp.toFixed(2),
              before: result.units_before ?? 0,
              target,
            })
          : t('addPosition.preview.noChange', { units: target })}
      </p>
      {result.price_warning && (
        <p role="alert" className="text-amber-400">
          {t('addPosition.preview.priceWarning', {
            message: result.price_warning.message,
          })}
        </p>
      )}
    </div>
  );
}

export function AddPositionForm({
  owner,
  accounts,
  defaultAccount,
  onAdded,
  onCollapse,
  controlsId,
}: Props) {
  const { t } = useTranslation();
  const { demoReadOnly, reason } = useDemoReadOnly();
  const [account, setAccount] = useState(defaultAccount ?? accounts[0] ?? '');
  const [ticker, setTicker] = useState('');
  const [mode, setMode] = useState<AmountMode>('unitsPrice');
  const [units, setUnits] = useState('');
  const [price, setPrice] = useState('');
  const [value, setValue] = useState('');
  const [date, setDate] = useState(todayIso);
  const [openingBalance, setOpeningBalance] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const values: FormValues = {
    owner,
    account,
    ticker,
    mode,
    units,
    price,
    value,
    date,
    openingBalance,
  };
  const valuesKey = JSON.stringify(values);
  const activePreview = preview?.key === valuesKey ? preview.result : null;

  const resetAmounts = () => {
    setTicker('');
    setUnits('');
    setPrice('');
    setValue('');
    setPreview(null);
  };

  // First submit previews the change; a second submit on unchanged inputs saves it.
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSuccess(null);
    const payload = buildPayload(values, t);
    if (typeof payload === 'string') {
      setError(payload);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (!activePreview) {
        setPreview({
          key: valuesKey,
          result: await createManualHolding({ ...payload, dry_run: true }),
        });
        return;
      }
      await createManualHolding({
        ...payload,
        confirm_price: Boolean(activePreview.price_warning),
      });
      setSuccess(t('addPosition.success'));
      resetAmounts();
      onAdded?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('addPosition.errors.generic')
      );
    } finally {
      setSubmitting(false);
    }
  };

  const submitLabel = submitting
    ? t('addPosition.submitting')
    : !activePreview
      ? t('addPosition.preview.button')
      : activePreview.price_warning
        ? t('addPosition.preview.saveAnyway')
        : t('addPosition.submit');

  return (
    <form
      id={controlsId}
      onSubmit={handleSubmit}
      aria-label={t('addPosition.title')}
      className="mb-6 rounded-lg border border-gray-800 bg-black/20 p-4"
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-white">
          {t('addPosition.title')}
        </h3>
        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            aria-label={t('addPosition.collapse')}
            aria-expanded="true"
            aria-controls={controlsId}
            className="inline-flex items-center gap-1.5 rounded border border-gray-700 px-2 py-0.5 text-sm text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 12 12"
              className="h-3 w-3"
              fill="none"
            >
              <path
                d="M2 6h8"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
            {t('addPosition.collapseShort')}
          </button>
        )}
      </div>
      <p className="mb-3 text-sm text-gray-400">{t('addPosition.totalHint')}</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm text-gray-300">
          {t('addPosition.account')}
          <select
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            className={inputClass}
          >
            {accounts.map((acct, index) => (
              <option key={`${acct}-${index}`} value={acct}>
                {acct}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-gray-300">
          {t('addPosition.ticker')}
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className={inputClass}
            placeholder="VWRL.L"
          />
        </label>
        <label className="text-sm text-gray-300">
          {t('addPosition.amountMode')}
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as AmountMode)}
            className={inputClass}
          >
            <option value="unitsPrice">{t('addPosition.unitsAndPrice')}</option>
            <option value="value">{t('addPosition.valueGbp')}</option>
          </select>
        </label>
        {mode === 'unitsPrice' ? (
          <div className="grid grid-cols-2 gap-2">
            <label className="text-sm text-gray-300">
              {t('addPosition.units')}
              <input
                type="number"
                min="0"
                step="any"
                value={units}
                onChange={(e) => setUnits(e.target.value)}
                className={inputClass}
              />
            </label>
            <label className="text-sm text-gray-300">
              {t('addPosition.priceGbp')}
              <input
                type="number"
                min="0"
                step="any"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className={inputClass}
              />
            </label>
          </div>
        ) : (
          <label className="text-sm text-gray-300">
            {t('addPosition.value')}
            <input
              type="number"
              min="0"
              step="any"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className={inputClass}
            />
          </label>
        )}
        <label className="text-sm text-gray-300">
          {t('addPosition.date')}
          <input
            type="date"
            value={date}
            max={todayIso()}
            disabled={openingBalance}
            onChange={(e) => setDate(e.target.value)}
            className={`${inputClass} disabled:opacity-60`}
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-300 sm:col-span-2 lg:col-span-3">
          <input
            type="checkbox"
            checked={openingBalance}
            onChange={(e) => setOpeningBalance(e.target.checked)}
          />
          {t('addPosition.openingBalance')}
        </label>
      </div>
      {activePreview && <PreviewSummary result={activePreview} />}
      <div className="mt-3 flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting || !account || demoReadOnly}
          title={reason()}
          className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
        >
          {submitLabel}
        </button>
        {error && (
          <span role="alert" className="text-sm text-red-500">
            {error}
          </span>
        )}
        {success && (
          <span role="status" className="text-sm text-green-500">
            {success}
          </span>
        )}
      </div>
    </form>
  );
}

export default AddPositionForm;
