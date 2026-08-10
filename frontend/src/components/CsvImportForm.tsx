import { useId, useState, type ChangeEvent, type FormEvent } from 'react';
import {
  importHoldingsCsv,
  reconcileHoldingsCsv,
  type ReconcileHoldingsCsvResponse,
} from '../api';

/** Provider keys supported by `backend/importers`, excluding the `test` stub. */
const PROVIDERS = [
  { value: 'degiro', label: 'DEGIRO' },
  { value: 'hargreaves', label: 'Hargreaves Lansdown' },
];

type Props = {
  owner: string;
  accountTypes: string[];
  onImported?: () => void;
};

type Status =
  | { kind: 'idle' }
  | { kind: 'submitting'; action: 'import' | 'reconcile' }
  | { kind: 'imported'; path: string }
  | { kind: 'reconciled'; result: ReconcileHoldingsCsvResponse }
  | { kind: 'error'; message: string };

const extractErrorMessage = (err: unknown): string => {
  if (err instanceof Error) return err.message;
  return 'Failed to process file. Please try again.';
};

const formatNumber = (value: number) => value.toLocaleString('en-GB');
const formatGbp = (value: number) =>
  value.toLocaleString('en-GB', { style: 'currency', currency: 'GBP' });
const formatDelta = (value: number, formatter = formatNumber) =>
  `${value > 0 ? '+' : ''}${formatter(value)}`;

type DiffSectionProps = {
  title: string;
  emptyMessage: string;
  rows: Array<{ ticker: string; detail: string }>;
};

function DiffSection({ title, emptyMessage, rows }: DiffSectionProps) {
  return (
    <section>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-300">
        {title}
      </h4>
      {rows.length === 0 ? (
        <p className="mt-1 text-sm text-gray-500">{emptyMessage}</p>
      ) : (
        <ul className="mt-1 divide-y divide-gray-800 rounded border border-gray-800">
          {rows.map(({ ticker, detail }) => (
            <li
              key={ticker}
              className="flex justify-between gap-3 px-2 py-1 text-sm"
            >
              <span className="font-medium text-white">{ticker}</span>
              <span className="text-right text-gray-300">{detail}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ReconciliationPreview({
  result,
}: {
  result: ReconcileHoldingsCsvResponse;
}) {
  const cash = result.cash_balance;
  return (
    <div
      role="status"
      aria-label="Reconciliation preview"
      className="mt-3 space-y-3 border-t border-gray-800 pt-3"
    >
      <div>
        <h3 className="font-semibold text-blue-300">Reconciliation preview</h3>
        <p className="text-sm text-gray-400">
          Preview only — no stored holdings were changed.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <DiffSection
          title="Added"
          emptyMessage="No holdings to add."
          rows={result.added.map((item) => ({
            ticker: item.ticker,
            detail: `${formatNumber(item.units)} units · ${formatGbp(item.value_gbp)}`,
          }))}
        />
        <DiffSection
          title="Removed"
          emptyMessage="No holdings to remove."
          rows={result.removed.map((item) => ({
            ticker: item.ticker,
            detail: `${formatNumber(item.units)} units · ${formatGbp(item.value_gbp)}`,
          }))}
        />
        <DiffSection
          title="Quantity changed"
          emptyMessage="No quantity changes."
          rows={result.quantity_changed.map((item) => ({
            ticker: item.ticker,
            detail: `${formatNumber(item.stored_units)} → ${formatNumber(item.imported_units)} (${formatDelta(item.delta)})`,
          }))}
        />
        <DiffSection
          title="Value changed"
          emptyMessage="No value changes."
          rows={result.value_changed.map((item) => ({
            ticker: item.ticker,
            detail: `${formatGbp(item.stored_value_gbp)} → ${formatGbp(item.imported_value_gbp)} (${formatDelta(item.delta_gbp, formatGbp)})`,
          }))}
        />
      </div>
      <section className="rounded border border-gray-800 p-2 text-sm">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-300">
          Cash balance
        </h4>
        <p className="mt-1 text-gray-300">
          {formatGbp(cash.stored_gbp)} → {formatGbp(cash.imported_gbp)} (
          {formatDelta(cash.delta_gbp, formatGbp)})
        </p>
      </section>
    </div>
  );
}

/** Upload and safely preview or import a CSV of holdings/transactions. */
export function CsvImportForm({ owner, accountTypes, onImported }: Props) {
  const [account, setAccount] = useState(accountTypes[0] ?? '');
  const [provider, setProvider] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const formId = useId();

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] ?? null);
    setStatus({ kind: 'idle' });
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!account || !provider || !file) return;
    const action = (e.nativeEvent as SubmitEvent).submitter?.getAttribute(
      'value'
    );

    if (action === 'reconcile') {
      setStatus({ kind: 'submitting', action: 'reconcile' });
      try {
        const result = await reconcileHoldingsCsv(
          owner,
          account,
          provider,
          file
        );
        setStatus({ kind: 'reconciled', result });
      } catch (err) {
        setStatus({ kind: 'error', message: extractErrorMessage(err) });
      }
      return;
    }

    setStatus({ kind: 'submitting', action: 'import' });
    try {
      const result = await importHoldingsCsv(owner, account, provider, file);
      setStatus({ kind: 'imported', path: result.path });
      setFile(null);
      onImported?.();
    } catch (err) {
      setStatus({ kind: 'error', message: extractErrorMessage(err) });
    }
  };

  const submitting = status.kind === 'submitting';
  const canSubmit = Boolean(account && provider && file) && !submitting;

  return (
    <div className="rounded-lg border border-gray-800 bg-black/20 p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Import CSV
      </p>
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
        <div>
          <label
            htmlFor={`${formId}-account`}
            className="block text-xs text-gray-400"
          >
            Account
          </label>
          <select
            id={`${formId}-account`}
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            className="rounded border border-gray-700 bg-gray-800 p-1 text-white"
          >
            {accountTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor={`${formId}-provider`}
            className="block text-xs text-gray-400"
          >
            Provider
          </label>
          <select
            id={`${formId}-provider`}
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded border border-gray-700 bg-gray-800 p-1 text-white"
          >
            <option value="">Select provider…</option>
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor={`${formId}-file`}
            className="block text-xs text-gray-400"
          >
            CSV file
          </label>
          <input
            id={`${formId}-file`}
            type="file"
            accept=".csv,text/csv"
            onChange={handleFileChange}
            className="text-white"
          />
        </div>
        <button
          type="submit"
          value="reconcile"
          disabled={!canSubmit}
          className="rounded border border-blue-600 px-3 py-1 text-blue-200 hover:bg-blue-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {status.kind === 'submitting' && status.action === 'reconcile'
            ? 'Reconciling…'
            : 'Reconcile (preview)'}
        </button>
        <button
          type="submit"
          value="import"
          disabled={!canSubmit}
          className="rounded border border-gray-700 px-3 py-1 text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {status.kind === 'submitting' && status.action === 'import'
            ? 'Importing…'
            : 'Import'}
        </button>
      </form>
      {status.kind === 'imported' && (
        <p role="status" className="mt-2 text-sm text-green-400">
          Imported successfully. Saved to {status.path}.
        </p>
      )}
      {status.kind === 'reconciled' && (
        <ReconciliationPreview result={status.result} />
      )}
      {status.kind === 'error' && (
        <p role="alert" className="mt-2 text-sm text-red-500">
          {status.message}
        </p>
      )}
    </div>
  );
}

export default CsvImportForm;
