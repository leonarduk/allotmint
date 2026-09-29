import { useCallback, useEffect, useState } from 'react';
import { getTransactions, splitTransaction, updateTransaction } from '../api';
import { useDemoReadOnly } from '../hooks/useDemoReadOnly';
import tableStyles from '../styles/table.module.css';
import type { Transaction } from '../types';
import {
  buildTransactionPayload,
  createTransactionFormValues,
  type TransactionFormValues,
} from './transactions/transactionForm';

type Props = { ticker: string };

type Mode =
  | { kind: 'edit'; id: string; values: TransactionFormValues }
  | { kind: 'split'; id: string; units: string };

const rowUnits = (tx: Transaction) => tx.units ?? tx.shares ?? null;

/**
 * Every transaction for one instrument across owners/accounts, with per-row
 * edit and split.  Editing goes through PUT /transactions/{id}; splitting
 * through POST /transactions/{id}/split.
 */
export function InstrumentTransactions({ ticker }: Props) {
  const { demoReadOnly, reason } = useDemoReadOnly();
  const [rows, setRows] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode | null>(null);
  const [saving, setSaving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getTransactions({ ticker })
      .then((data) => {
        if (!active) return;
        setRows(data);
        setError(null);
      })
      .catch((err) => {
        if (active)
          setError(
            err instanceof Error ? err.message : 'Failed to load transactions.'
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [ticker, refreshKey]);

  const run = useCallback(
    async (action: () => Promise<unknown>, failure: string) => {
      setSaving(true);
      setError(null);
      try {
        await action();
        setMode(null);
        setRefreshKey((k) => k + 1);
      } catch (err) {
        setError(err instanceof Error ? err.message : failure);
      } finally {
        setSaving(false);
      }
    },
    []
  );

  const saveEdit = (tx: Transaction, values: TransactionFormValues) => {
    const built = buildTransactionPayload(values, tx.owner, tx.account ?? '');
    if (built.error !== null) {
      setError(built.error);
      return;
    }
    void run(
      () => updateTransaction(tx.id as string, built.payload),
      'Failed to update transaction.'
    );
  };

  const saveSplit = (tx: Transaction, unitsText: string) => {
    const first = Number(unitsText);
    const total = Number(rowUnits(tx));
    if (!Number.isFinite(first) || first <= 0 || first >= total) {
      setError(`Enter units greater than 0 and less than ${total}.`);
      return;
    }
    void run(
      () => splitTransaction(tx.id as string, first),
      'Failed to split transaction.'
    );
  };

  const disabledReason = reason();

  return (
    <div style={{ marginBottom: '1rem' }}>
      {error && (
        <div role="alert" style={{ color: 'red', marginBottom: '0.5rem' }}>
          {error}
        </div>
      )}
      <table className={tableStyles.table} style={{ fontSize: '0.85rem' }}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>Date</th>
            <th className={tableStyles.cell}>Owner</th>
            <th className={tableStyles.cell}>Account</th>
            <th className={tableStyles.cell}>Type</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>
              Units
            </th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>
              Price £
            </th>
            <th className={tableStyles.cell}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td className={tableStyles.cell} colSpan={7}>
                Loading…
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td className={tableStyles.cell} colSpan={7}>
                No transactions for {ticker}.
              </td>
            </tr>
          ) : (
            rows.map((tx) => {
              const active = mode && mode.id === tx.id ? mode : null;
              const canAct = Boolean(tx.id) && !demoReadOnly;
              return (
                <tr key={tx.id ?? `${tx.owner}-${tx.date}-${rowUnits(tx)}`}>
                  {active?.kind === 'edit' ? (
                    <EditCells
                      values={active.values}
                      saving={saving}
                      onChange={(values) => setMode({ ...active, values })}
                      onSave={() => saveEdit(tx, active.values)}
                      onCancel={() => setMode(null)}
                    />
                  ) : (
                    <>
                      <td className={tableStyles.cell}>{tx.date ?? ''}</td>
                      <td className={tableStyles.cell}>{tx.owner}</td>
                      <td className={tableStyles.cell}>
                        {(tx.account ?? '').toUpperCase()}
                      </td>
                      <td className={tableStyles.cell}>{tx.type ?? ''}</td>
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                      >
                        {rowUnits(tx) ?? ''}
                      </td>
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                      >
                        {tx.price_gbp ?? ''}
                      </td>
                      <td className={tableStyles.cell}>
                        {active?.kind === 'split' ? (
                          <span>
                            <input
                              aria-label="Units in first part"
                              type="number"
                              value={active.units}
                              style={{ width: '6rem' }}
                              onChange={(e) =>
                                setMode({ ...active, units: e.target.value })
                              }
                            />{' '}
                            <button
                              type="button"
                              disabled={saving}
                              onClick={() => saveSplit(tx, active.units)}
                            >
                              Confirm split
                            </button>{' '}
                            <button type="button" onClick={() => setMode(null)}>
                              Cancel
                            </button>
                          </span>
                        ) : (
                          <span title={disabledReason}>
                            <button
                              type="button"
                              disabled={!canAct}
                              onClick={() =>
                                setMode({
                                  kind: 'edit',
                                  id: tx.id as string,
                                  values: createTransactionFormValues(tx),
                                })
                              }
                            >
                              Edit
                            </button>{' '}
                            <button
                              type="button"
                              disabled={!canAct || !rowUnits(tx)}
                              onClick={() =>
                                setMode({
                                  kind: 'split',
                                  id: tx.id as string,
                                  units: '',
                                })
                              }
                            >
                              Split
                            </button>
                          </span>
                        )}
                      </td>
                    </>
                  )}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

type EditCellsProps = {
  values: TransactionFormValues;
  saving: boolean;
  onChange: (values: TransactionFormValues) => void;
  onSave: () => void;
  onCancel: () => void;
};

function EditCells({
  values,
  saving,
  onChange,
  onSave,
  onCancel,
}: EditCellsProps) {
  const field = (
    key: keyof TransactionFormValues,
    label: string,
    type = 'text'
  ) => (
    <input
      aria-label={label}
      type={type}
      value={values[key]}
      style={{ width: '100%' }}
      onChange={(e) => onChange({ ...values, [key]: e.target.value })}
    />
  );
  return (
    <>
      <td className={tableStyles.cell}>{field('date', 'Date', 'date')}</td>
      <td className={tableStyles.cell} colSpan={3}>
        {field('reason', 'Reason')}
      </td>
      <td className={tableStyles.cell}>{field('units', 'Units', 'number')}</td>
      <td className={tableStyles.cell}>{field('price', 'Price', 'number')}</td>
      <td className={tableStyles.cell}>
        <button type="button" disabled={saving} onClick={onSave}>
          Save
        </button>{' '}
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </td>
    </>
  );
}
