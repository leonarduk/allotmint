import { useEffect, useMemo, useState } from "react";
import { getOwners, getPortfolio, getRebalance } from "../api";
import type { OwnerSummary, Portfolio, TradeSuggestion } from "../types";
import EmptyState from "../components/EmptyState";
import { sanitizeOwners } from "../utils/owners";
import { useRoute } from "../RouteContext";

type Row = { ticker: string; current: string; target: string };
type ParsedRow = { currentValue: number; targetWeightPct: number };
type TradeRow = TradeSuggestion & { currentWeightPct: number; targetWeightPct: number };

const BLANK_ROW: Row = { ticker: "", current: "", target: "" };
const percentFormatter = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function rowsFromPortfolio(portfolio: Portfolio): Row[] {
  const totalsByTicker = new Map<string, number>();

  for (const account of portfolio.accounts) {
    for (const holding of account.holdings) {
      const ticker = holding.ticker?.trim().toUpperCase();
      if (!ticker) continue;
      // Use market_value_gbp (GBP-denominated) as the primary source.
      // Fall back to units * price only when price is expected to be GBP (e.g. LSE).
      // market_value_currency is intentionally excluded: it is not guaranteed to be GBP
      // and mixing currencies produces incorrect weights and invalid trade suggestions.
      const value =
        holding.market_value_gbp ??
        (holding.price != null ? holding.units * holding.price : null);
      if (value == null || !Number.isFinite(value) || value <= 0) continue;
      totalsByTicker.set(ticker, (totalsByTicker.get(ticker) ?? 0) + value);
    }
  }

  const entries = [...totalsByTicker.entries()].sort((a, b) => b[1] - a[1]);
  if (!entries.length) return [BLANK_ROW];

  const totalValue = entries.reduce((sum, [, value]) => sum + value, 0);
  return entries.map(([ticker, current]) => ({
    ticker,
    current: current.toFixed(2),
    target: totalValue > 0 ? ((current / totalValue) * 100).toFixed(2) : "0",
  }));
}

export default function Rebalance() {
  const route = useRoute();
  const [rows, setRows] = useState<Row[]>([BLANK_ROW]);
  const [trades, setTrades] = useState<TradeSuggestion[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [ownersLoading, setOwnersLoading] = useState(true);
  const [ownersError, setOwnersError] = useState<string | null>(null);
  const [selectedOwner, setSelectedOwner] = useState("");
  const [isPrefilling, setIsPrefilling] = useState(false);

  const parsedRows = useMemo(() => {
    const parsed = new Map<string, ParsedRow>();
    for (const row of rows) {
      const ticker = row.ticker.trim().toUpperCase();
      if (!ticker) continue;
      const currentValue = parseFloat(row.current);
      const targetWeightPct = parseFloat(row.target);
      if (!Number.isFinite(currentValue) || !Number.isFinite(targetWeightPct)) continue;
      parsed.set(ticker, { currentValue, targetWeightPct });
    }
    return parsed;
  }, [rows]);

  const totalCurrentValue = useMemo(
    () =>
      [...parsedRows.values()].reduce(
        (sum, parsed) => sum + Math.max(parsed.currentValue, 0),
        0,
      ),
    [parsedRows],
  );
  const totalTargetWeightPct = useMemo(
    () =>
      [...parsedRows.values()].reduce(
        (sum, parsed) => sum + parsed.targetWeightPct,
        0,
      ),
    [parsedRows],
  );

  const tradeRows = useMemo<TradeRow[] | null>(() => {
    if (!trades) return null;
    return trades.map((trade) => {
      const parsed = parsedRows.get(trade.ticker);
      const currentWeightPct =
        parsed && totalCurrentValue > 0 ? (parsed.currentValue / totalCurrentValue) * 100 : 0;
      const targetWeightPct = parsed?.targetWeightPct ?? 0;
      return {
        ...trade,
        currentWeightPct,
        targetWeightPct,
      };
    });
  }, [parsedRows, totalCurrentValue, trades]);

  useEffect(() => {
    let cancelled = false;
    setOwnersLoading(true);
    setOwnersError(null);
    getOwners()
      .then((list) => {
        if (cancelled) return;
        const sanitized = sanitizeOwners(Array.isArray(list) ? list : []);
        setOwners(sanitized);
      })
      .catch((error) => {
        if (cancelled) return;
        setOwners([]);
        setOwnersError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!cancelled) setOwnersLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const availableOwner = useMemo(() => {
    if (!owners.length) return "";
    const routeOwner = route.selectedOwner?.trim();
    if (routeOwner && owners.some((owner) => owner.owner === routeOwner)) {
      return routeOwner;
    }
    return owners[0].owner;
  }, [owners, route.selectedOwner]);

  useEffect(() => {
    if (!availableOwner) return;
    setSelectedOwner((current) => current || availableOwner);
  }, [availableOwner]);

  useEffect(() => {
    if (!selectedOwner) return;

    let cancelled = false;
    setIsPrefilling(true);
    setErr(null);

    getPortfolio(selectedOwner)
      .then((portfolio) => {
        if (cancelled) return;
        setRows(rowsFromPortfolio(portfolio));
        setTrades(null);
      })
      .catch((error) => {
        if (cancelled) return;
        setErr(
          `Unable to prefill portfolio holdings for ${selectedOwner}: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      })
      .finally(() => {
        if (!cancelled) setIsPrefilling(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedOwner]);

  const addRow = () =>
    setRows((prev) => [...prev, { ticker: "", current: "", target: "" }]);

  const removeRow = (index: number) =>
    setRows((prev) => prev.filter((_, i) => i !== index));

  const updateRow = (index: number, field: keyof Row, value: string) =>
    setRows((r) => r.map((row, i) => (i === index ? { ...row, [field]: value } : row)));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const actual: Record<string, number> = {};
    const target: Record<string, number> = {};
    const validRows: Array<{ ticker: string; current: number; weightPct: number }> = [];

    for (const row of rows) {
      if (!row.ticker) {
        continue;
      }
      const current = parseFloat(row.current);
      const weightPct = parseFloat(row.target);
      if (Number.isNaN(current) || Number.isNaN(weightPct)) {
        setErr("Please enter valid numbers for current value and target weight.");
        setTrades(null);
        return;
      }
      const normalizedTicker = row.ticker.trim().toUpperCase();
      if (!normalizedTicker) continue;
      validRows.push({ ticker: normalizedTicker, current, weightPct });
    }

    const totalInputCurrent = validRows.reduce((sum, row) => sum + row.current, 0);
    const totalInputTargetPct = validRows.reduce((sum, row) => sum + row.weightPct, 0);
    if (Math.abs(totalInputTargetPct - 100) > 0.01) {
      setErr(
        `Target weights must total 100%. Current total is ${percentFormatter.format(totalInputTargetPct)}%.`,
      );
      setTrades(null);
      return;
    }

    for (const row of validRows) {
      const exactCurrentWeightPct = totalInputCurrent > 0 ? (row.current / totalInputCurrent) * 100 : 0;
      const roundedCurrentWeightPct = Number(exactCurrentWeightPct.toFixed(2));
      const targetWeight =
        Math.abs(row.weightPct - roundedCurrentWeightPct) < 1e-9
          ? exactCurrentWeightPct / 100
          : row.weightPct / 100;
      actual[row.ticker] = row.current;
      target[row.ticker] = targetWeight;
    }

    try {
      const res = await getRebalance(actual, target);
      setTrades(res);
      setErr(null);
    } catch (error) {
      setTrades(null);
      setErr(String(error));
    }
  }

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">Rebalance Portfolio</h1>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
        Holdings are prefilled from your selected portfolio. You can edit values manually to run
        custom or hypothetical rebalance scenarios.
      </p>
      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        Target weight is entered as a percent (for example, 20 means 20%).
      </p>
      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        Keeping a target equal to the shown current weight is treated as no-change for that ticker.
      </p>
      <p
        className={`mb-4 text-xs ${
          Math.abs(totalTargetWeightPct - 100) <= 0.01
            ? "text-emerald-600 dark:text-emerald-400"
            : "text-amber-600 dark:text-amber-400"
        }`}
      >
        Total target weight: {percentFormatter.format(totalTargetWeightPct)}%
        {Math.abs(totalTargetWeightPct - 100) <= 0.01
          ? " (ready to rebalance)"
          : " (must equal 100%)"}
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium" htmlFor="rebalance-owner-select">
          Portfolio owner
        </label>
        <select
          id="rebalance-owner-select"
          className="rounded border p-1"
          value={selectedOwner}
          onChange={(e) => {
            const owner = e.target.value;
            setSelectedOwner(owner);
            route.setSelectedOwner(owner);
          }}
          disabled={ownersLoading || owners.length === 0}
        >
          {owners.length === 0 && <option value="">No owners</option>}
          {owners.map((owner) => (
            <option key={owner.owner} value={owner.owner}>
              {owner.owner}
            </option>
          ))}
        </select>
        {ownersLoading && <span className="text-xs text-slate-500">Loading owners…</span>}
        {isPrefilling && <span className="text-xs text-slate-500">Loading holdings…</span>}
      </div>
      {ownersError && <p className="mb-4 text-sm text-red-600">{ownersError}</p>}

      <form onSubmit={handleSubmit} className="mb-4 flex flex-col gap-2">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Current value</th>
              <th>Current weight</th>
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
                    onChange={(e) => updateRow(idx, "ticker", e.target.value)}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="any"
                    className="w-full border p-1"
                    value={row.current}
                    onChange={(e) => updateRow(idx, "current", e.target.value)}
                  />
                </td>
                <td>
                  <input
                    type="text"
                    className="w-full border p-1 opacity-80"
                    value={
                      Number.isFinite(parseFloat(row.current)) && totalCurrentValue > 0
                        ? `${percentFormatter.format((parseFloat(row.current) / totalCurrentValue) * 100)}%`
                        : "—"
                    }
                    readOnly
                    aria-label={`Current weight for ${row.ticker || `row ${idx + 1}`}`}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="any"
                    className="w-full border p-1"
                    value={row.target}
                    onChange={(e) => updateRow(idx, "target", e.target.value)}
                    aria-label={`Target weight (%) for ${row.ticker || `row ${idx + 1}`}`}
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
      {tradeRows && tradeRows.length > 0 && (
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Current weight</th>
              <th>Target weight</th>
              <th>Action</th>
              <th>Trade value</th>
            </tr>
          </thead>
          <tbody>
            {tradeRows.map((t) => (
              <tr key={t.ticker}>
                <td>{t.ticker}</td>
                <td>{percentFormatter.format(t.currentWeightPct)}%</td>
                <td>{percentFormatter.format(t.targetWeightPct)}%</td>
                <td className={t.action === "buy" ? "text-green-600" : "text-red-600"}>
                  {t.action.toUpperCase()}
                </td>
                <td>{t.amount.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {tradeRows && tradeRows.length > 0 && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          Trade value is the amount of portfolio value to buy or sell for each ticker (not number
          of units/shares).
        </p>
      )}
      {trades && trades.length === 0 && <EmptyState message="No trades required." />}
    </div>
  );
}
