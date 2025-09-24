import { useState } from 'react';
import { getRebalance } from '../api';
import type { TradeSuggestion } from '../types';
import EmptyState from '../components/EmptyState';

type Row = { ticker: string; current: string; target: string };

export default function Rebalance() {
  const [rows, setRows] = useState<Row[]>([
    { ticker: 'PFE', current: '4000', target: '0.4' },
    { ticker: 'MSFT', current: '3000', target: '0.4' },
    { ticker: 'CASH', current: '3000', target: '0' },
    { ticker: 'GOOG', current: '0', target: '0.2' },
  ]);
  const [trades, setTrades] = useState<TradeSuggestion[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const addRow = () =>
    setRows([...rows, { ticker: '', current: '', target: '' }]);

  const removeRow = (index: number) =>
    setRows(rows.filter((_, i) => i !== index));

  const updateRow = (index: number, field: keyof Row, value: string) =>
    setRows((r) =>
      r.map((row, i) => (i === index ? { ...row, [field]: value } : row))
    );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const actual: Record<string, number> = {};
    const target: Record<string, number> = {};

    for (const row of rows) {
      if (!row.ticker) {
        continue;
      }
      const current = parseFloat(row.current);
      const weight = parseFloat(row.target);
      if (Number.isNaN(current) || Number.isNaN(weight)) {
        setErr(
          'Please enter valid numbers for current value and target weight.'
        );
        setTrades(null);
        return;
      }
      actual[row.ticker] = current;
      target[row.ticker] = weight;
    }

    try {
      const res = await getRebalance(actual, target);
      setTrades(res);
      setErr(null);
    } catch (e) {
      setTrades(null);
      setErr(String(e));
    }
  }

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">Rebalance Portfolio</h1>
      <form onSubmit={handleSubmit} className="mb-4 flex flex-col gap-2">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Current value</th>
              <th>Target weight</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx}>
                <td>
                  <input
                    type="text"
                    className="w-full border p-1"
                    value={row.ticker}
                    onChange={(e) => updateRow(idx, 'ticker', e.target.value)}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="any"
                    className="w-full border p-1"
                    value={row.current}
                    onChange={(e) => updateRow(idx, 'current', e.target.value)}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="any"
                    className="w-full border p-1"
                    value={row.target}
                    onChange={(e) => updateRow(idx, 'target', e.target.value)}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="text-red-600"
                    onClick={() => removeRow(idx)}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={addRow}
            className="rounded bg-gray-200 px-2 py-1"
          >
            Add ticker
          </button>
          <button
            type="submit"
            className="rounded bg-blue-500 px-4 py-2 text-white"
          >
            Rebalance
          </button>
        </div>
      </form>
      {err && <p className="text-red-600">{err}</p>}
      {trades && trades.length > 0 && (
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Action</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.ticker}>
                <td>{t.ticker}</td>
                <td
                  className={
                    t.action === 'buy' ? 'text-green-600' : 'text-red-600'
                  }
                >
                  {t.action.toUpperCase()}
                </td>
                <td>{t.amount.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {trades && trades.length === 0 && (
        <EmptyState message="No trades required." />
      )}
    </div>
  );
}
