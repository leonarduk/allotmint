import {
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import {
  applyStatementSuggestion,
  getReconciliationProvider,
  reconcileStatement,
  type ReconciliationProvider,
  type StatementDiff,
  type StatementReconciliation,
} from '../api';
import { useDemoReadOnly } from '../hooks/useDemoReadOnly';
import { money } from '../lib/money';

type Props = {
  owner: string;
  accountTypes: string[];
  /** Called after an accepted suggestion has been written to the ledger. */
  onApplied?: () => void;
};

type Status =
  | { kind: 'idle' }
  | { kind: 'submitting' }
  | { kind: 'done'; result: StatementReconciliation; id: number }
  | { kind: 'error'; message: string };

/** Per-difference review state; nothing is written until a row is confirmed. */
type RowState =
  | { kind: 'open' }
  | { kind: 'confirming' }
  | { kind: 'applying' }
  | { kind: 'applied' }
  | { kind: 'dismissing'; reason: string }
  | { kind: 'dismissed'; reason: string }
  | { kind: 'failed'; message: string };

/** Pence to pounds: reconciliation amounts always arrive as integer pence. */
const formatMinor = (minor: number | null) =>
  money(minor === null ? null : minor / 100);

const errorMessage = (err: unknown, fallback: string) =>
  err instanceof Error ? err.message : fallback;

function PrivacyNotice({
  provider,
}: {
  provider: ReconciliationProvider | null;
}) {
  const { t } = useTranslation();
  if (!provider) return null;
  return (
    <p
      role="note"
      className={`mb-2 text-xs ${provider.sent_to_cloud ? 'text-amber-300' : 'text-gray-400'}`}
    >
      {provider.sent_to_cloud
        ? t('statementReconcile.cloudNotice', {
            provider: provider.llm_provider,
          })
        : t('statementReconcile.localNotice', {
            provider: provider.llm_provider,
          })}
    </p>
  );
}

type DiffRowProps = {
  diff: StatementDiff;
  state: RowState;
  readOnly: boolean;
  onChange: (state: RowState) => void;
  onAccept: () => void;
};

function DiffActions({
  diff,
  state,
  readOnly,
  onChange,
  onAccept,
}: DiffRowProps) {
  const { t } = useTranslation();
  const button =
    'rounded border px-2 py-0.5 text-xs disabled:cursor-not-allowed disabled:opacity-50';
  switch (state.kind) {
    case 'applied':
      return (
        <span className="text-xs text-green-400">
          {t('statementReconcile.applied')}
        </span>
      );
    case 'applying':
      return (
        <span className="text-xs text-gray-400">
          {t('statementReconcile.applying')}
        </span>
      );
    case 'dismissed':
      return (
        <span className="text-xs text-gray-500">
          {t('statementReconcile.dismissedWith', { reason: state.reason })}
        </span>
      );
    case 'confirming':
      return (
        <span className="flex flex-wrap gap-1">
          <button
            type="button"
            className={`${button} border-green-600 text-green-200`}
            onClick={onAccept}
          >
            {t('statementReconcile.confirm')}
          </button>
          <button
            type="button"
            className={`${button} border-gray-700 text-gray-300`}
            onClick={() => onChange({ kind: 'open' })}
          >
            {t('statementReconcile.cancel')}
          </button>
        </span>
      );
    case 'dismissing':
      return (
        <span className="flex flex-wrap gap-1">
          <input
            aria-label={t('statementReconcile.dismissReason')}
            placeholder={t('statementReconcile.dismissReason')}
            value={state.reason}
            onChange={(e) =>
              onChange({ kind: 'dismissing', reason: e.target.value })
            }
            className="rounded border border-gray-700 bg-gray-800 px-1 text-xs text-white"
          />
          <button
            type="button"
            disabled={!state.reason.trim()}
            className={`${button} border-gray-600 text-gray-200`}
            onClick={() =>
              onChange({ kind: 'dismissed', reason: state.reason.trim() })
            }
          >
            {t('statementReconcile.dismiss')}
          </button>
        </span>
      );
    default:
      return (
        <span className="flex flex-wrap gap-1">
          {diff.suggestion.request && (
            <button
              type="button"
              disabled={readOnly}
              className={`${button} border-blue-600 text-blue-200`}
              onClick={() => onChange({ kind: 'confirming' })}
            >
              {t('statementReconcile.accept')}
            </button>
          )}
          <button
            type="button"
            className={`${button} border-gray-700 text-gray-300`}
            onClick={() => onChange({ kind: 'dismissing', reason: '' })}
          >
            {t('statementReconcile.dismiss')}
          </button>
          {state.kind === 'failed' && (
            <span role="alert" className="text-xs text-red-400">
              {state.message}
            </span>
          )}
        </span>
      );
  }
}

function DiffRow(props: DiffRowProps) {
  const { t } = useTranslation();
  const { diff } = props;
  return (
    <tr className="align-top">
      <td className="px-2 py-1 text-gray-300">
        {t(`statementReconcile.kinds.${diff.kind}`)}
      </td>
      <td className="px-2 py-1 text-gray-400">{diff.date ?? '—'}</td>
      <td className="px-2 py-1 text-white">
        {diff.message}
        <div className="text-xs text-gray-400">
          {diff.suggestion.description}
        </div>
      </td>
      <td className="px-2 py-1 text-right text-gray-300">
        {formatMinor(diff.statement_minor)}
      </td>
      <td className="px-2 py-1 text-right text-gray-300">
        {formatMinor(diff.ledger_minor)}
      </td>
      <td className="px-2 py-1">
        <DiffActions {...props} />
      </td>
    </tr>
  );
}

function ReconciliationResult({
  result,
  readOnly,
  onApplied,
}: {
  result: StatementReconciliation;
  readOnly: boolean;
  onApplied?: () => void;
}) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<RowState[]>(() =>
    result.diffs.map(() => ({ kind: 'open' }))
  );
  const setRow = (index: number, state: RowState) =>
    setRows((current) => current.map((row, i) => (i === index ? state : row)));

  const accept = async (index: number) => {
    const request = result.diffs[index].suggestion.request;
    if (!request) return;
    setRow(index, { kind: 'applying' });
    try {
      await applyStatementSuggestion(request);
      setRow(index, { kind: 'applied' });
      onApplied?.();
    } catch (err) {
      setRow(index, {
        kind: 'failed',
        message: errorMessage(err, t('statementReconcile.applyFailed')),
      });
    }
  };

  const warnings = result.warnings;
  return (
    <div
      role="status"
      aria-label={t('statementReconcile.resultTitle')}
      className="mt-3 space-y-3 border-t border-gray-800 pt-3"
    >
      <p className="text-sm text-gray-300">
        {t('statementReconcile.summary', {
          rows: result.extracted.rows.length,
          matched: result.matched.length,
          diffs: result.diffs.length,
        })}
      </p>
      {warnings.length > 0 && (
        <ul
          aria-label={t('statementReconcile.warnings')}
          className="list-disc pl-5 text-xs text-amber-300"
        >
          {warnings.map((warning, i) => (
            <li key={`${i}-${warning}`}>{warning}</li>
          ))}
        </ul>
      )}
      {result.diffs.length === 0 ? (
        <p className="text-sm text-green-400">
          {t('statementReconcile.noDiffs')}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-gray-400">
              <tr>
                <th className="px-2 py-1">
                  {t('statementReconcile.columns.kind')}
                </th>
                <th className="px-2 py-1">
                  {t('statementReconcile.columns.date')}
                </th>
                <th className="px-2 py-1">
                  {t('statementReconcile.columns.detail')}
                </th>
                <th className="px-2 py-1 text-right">
                  {t('statementReconcile.columns.statement')}
                </th>
                <th className="px-2 py-1 text-right">
                  {t('statementReconcile.columns.ledger')}
                </th>
                <th className="px-2 py-1">
                  {t('statementReconcile.columns.action')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {result.diffs.map((diff, index) => (
                <DiffRow
                  key={`${diff.kind}-${diff.statement_index ?? ''}-${diff.ledger_id ?? ''}-${index}`}
                  diff={diff}
                  state={rows[index]}
                  readOnly={readOnly}
                  onChange={(state) => setRow(index, state)}
                  onAccept={() => accept(index)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {result.explanation && (
        <section className="rounded border border-gray-800 p-2 text-sm">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-300">
            {t('statementReconcile.explanation')}
          </h4>
          <p className="mt-1 whitespace-pre-wrap text-gray-300">
            {result.explanation}
          </p>
        </section>
      )}
    </div>
  );
}

/**
 * Upload a broker statement or contract note, see how it differs from the
 * ledger, and apply suggested fixes one confirmed row at a time (#10474).
 */
export function StatementReconcilePanel({
  owner,
  accountTypes,
  onApplied,
}: Props) {
  const { t } = useTranslation();
  const { demoReadOnly } = useDemoReadOnly();
  const formId = useId();
  const [account, setAccount] = useState(accountTypes[0] ?? '');
  const [file, setFile] = useState<File | null>(null);
  const [explain, setExplain] = useState(false);
  const [provider, setProvider] = useState<ReconciliationProvider | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  // Bumped when the inputs change so a slow response for an old selection
  // cannot overwrite the current one.
  const requestIdRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    getReconciliationProvider()
      .then((value) => {
        if (!cancelled) setProvider(value);
      })
      .catch(() => {
        if (!cancelled) setProvider(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const reset = () => {
    requestIdRef.current += 1;
    setStatus({ kind: 'idle' });
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!account || !file) return;
    const requestId = ++requestIdRef.current;
    setStatus({ kind: 'submitting' });
    try {
      const result = await reconcileStatement(owner, account, file, explain);
      if (requestIdRef.current === requestId)
        setStatus({ kind: 'done', result, id: requestId });
    } catch (err) {
      if (requestIdRef.current === requestId) {
        setStatus({
          kind: 'error',
          message: errorMessage(err, t('statementReconcile.failed')),
        });
      }
    }
  };

  const submitting = status.kind === 'submitting';
  return (
    <div className="rounded-lg border border-gray-800 bg-black/20 p-3">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
        {t('statementReconcile.title')}
      </p>
      <p className="mb-2 text-xs text-gray-400">
        {t('statementReconcile.intro')}
      </p>
      <PrivacyNotice provider={provider} />
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
        <div>
          <label
            htmlFor={`${formId}-account`}
            className="block text-xs text-gray-400"
          >
            {t('statementReconcile.account')}
          </label>
          <select
            id={`${formId}-account`}
            value={account}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => {
              setAccount(e.target.value);
              reset();
            }}
            className="rounded border border-gray-700 bg-gray-800 p-1 text-white"
          >
            {accountTypes.map((type, index) => (
              <option key={`${type}-${index}`} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor={`${formId}-file`}
            className="block text-xs text-gray-400"
          >
            {t('statementReconcile.file')}
          </label>
          <input
            id={`${formId}-file`}
            type="file"
            accept=".pdf,.csv,.txt,application/pdf,text/csv,text/plain"
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              setFile(e.target.files?.[0] ?? null);
              reset();
            }}
            className="text-white"
          />
        </div>
        <label className="flex items-center gap-1 text-xs text-gray-300">
          <input
            type="checkbox"
            checked={explain}
            onChange={(e) => setExplain(e.target.checked)}
          />
          {t('statementReconcile.explainUnmatched')}
        </label>
        <button
          type="submit"
          disabled={!account || !file || submitting}
          className="rounded border border-blue-600 px-3 py-1 text-blue-200 hover:bg-blue-950 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting
            ? t('statementReconcile.reconciling')
            : t('statementReconcile.reconcile')}
        </button>
      </form>
      {status.kind === 'done' && (
        <ReconciliationResult
          key={status.id}
          result={status.result}
          readOnly={demoReadOnly}
          onApplied={onApplied}
        />
      )}
      {status.kind === 'error' && (
        <p role="alert" className="mt-2 text-sm text-red-500">
          {status.message}
        </p>
      )}
    </div>
  );
}

export default StatementReconcilePanel;
