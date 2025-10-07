import { Suspense, useState, useEffect } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Portfolio, Account } from "../types";
import { AccountBlock } from "./AccountBlock";
import { ValueAtRisk } from "./ValueAtRisk";
import { money } from "../lib/money";
import { formatDateISO } from "../lib/date";
import { useConfig } from "../ConfigContext";
import { complianceForOwner } from "../api";
import { getGrowthStage } from "../utils/growthStage";
import lazyWithDelay from "../utils/lazyWithDelay";
import PortfolioDashboardSkeleton from "./skeletons/PortfolioDashboardSkeleton";

const PerformanceDashboard = lazyWithDelay(
  () => import("@/components/PerformanceDashboard"),
);

// Props accepted by the view. `data` is null until a portfolio is loaded.
type Props = {
  data: Portfolio | null;
  loading?: boolean;
  error?: string | null;
  onDateChange?: (isoDate: string | null) => void;
};

/**
 * Render a portfolio tree showing an owner's accounts and holdings.
 *
 * The component is intentionally tiny: it deals only with presentation and
 * relies on its parent for data fetching. Conditional branches early-return to
 * keep the JSX at the bottom easy to follow.
 */
export function PortfolioView({ data, loading, error, onDateChange }: Props) {
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);
  const [hasWarnings, setHasWarnings] = useState(false);
  const [pendingDate, setPendingDate] = useState<string>("");
  const { baseCurrency } = useConfig();

  const accountKey = (acct: Account, idx: number) => `${acct.account_type}-${idx}`;

  useEffect(() => {
    setSelectedAccounts(data ? data.accounts.map(accountKey) : []);
  }, [data]);

  useEffect(() => {
    setPendingDate(data?.as_of ?? "");
  }, [data?.as_of]);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      if (!data?.owner) {
        setHasWarnings(false);
        return;
      }
      try {
        const res = await complianceForOwner(data.owner);
        if (!cancelled) setHasWarnings(res.warnings.length > 0);
      } catch {
        if (!cancelled) setHasWarnings(false);
      }
    }
    check();
    return () => {
      cancelled = true;
    };
  }, [data?.owner]);

  if (loading) return <div>Loading portfolio…</div>; // show a quick spinner
  if (error) return <div className="text-error">{error}</div>; // bubble errors
  if (!data) return <div>Select an owner.</div>; // nothing chosen yet

  const allKeys = data.accounts.map(accountKey);
  const activeSet = new Set(
    selectedAccounts.length ? selectedAccounts : allKeys
  );

  const totalValue = data.accounts.reduce(
    (sum, acct, idx) =>
      activeSet.has(accountKey(acct, idx))
        ? sum + acct.value_estimate_gbp
        : sum,
    0
  );

  const asOfDate = data.as_of ? new Date(data.as_of) : null;
  const todayIso = formatDateISO(new Date());
  const daysSince = asOfDate
    ? Math.floor((Date.now() - asOfDate.getTime()) / (1000 * 60 * 60 * 24))
    : 0;
  const showForward7d = daysSince >= 7;
  const showForward30d = daysSince >= 30;

  const handleDateSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = pendingDate.trim();
    onDateChange?.(trimmed ? trimmed : null);
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section className="rounded-lg border border-gray-800 bg-gray-900/70 p-4 md:p-6">
          <form
            onSubmit={handleDateSubmit}
            className="mb-4 flex flex-wrap items-center gap-2 text-sm text-gray-300"
          >
            <label htmlFor="portfolio-as-of" className="flex items-center gap-2">
              <span>As of</span>
              <input
                id="portfolio-as-of"
                type="date"
                value={pendingDate}
                max={todayIso}
                onChange={(e) => setPendingDate(e.target.value)}
                className="rounded border border-gray-700 bg-gray-800 p-1 text-white"
              />
            </label>
            <button
              type="submit"
              className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
            >
              Go
            </button>
            {data.as_of && (
              <span className="text-xs text-gray-400">
                Showing {formatDateISO(new Date(data.as_of))}
              </span>
            )}
          </form>
          <div className="mb-6 text-lg font-semibold text-white">
            Approx Total: {money(totalValue, baseCurrency)}
          </div>
          {hasWarnings && (
            <div className="mb-4">
              <Link
                to={`/compliance/${data.owner}`}
                className="text-blue-400 hover:text-blue-300"
              >
                View compliance warnings
              </Link>
            </div>
          )}
          <div className="mb-6 rounded-lg border border-gray-800 bg-black/30 p-4">
            <ValueAtRisk owner={data.owner} />
          </div>
          <div className="space-y-4">
            {data.accounts.map((acct, idx) => {
              const key = accountKey(acct, idx);
              const checked = activeSet.has(key);
              const order: Record<string, number> = {
                seed: 0,
                growing: 1,
                harvest: 2,
              };
              const stageInfo = acct.holdings.reduce(
                (prev, h) => {
                  const s = getGrowthStage({ daysHeld: h.days_held });
                  return order[s.stage] > order[prev.stage] ? s : prev;
                },
                getGrowthStage({})
              );
              return (
                <div key={key} className="flex items-start">
                  <span className="mr-2" title={stageInfo.message}>
                    {stageInfo.icon}
                  </span>
                  <AccountBlock
                    account={acct}
                    selected={checked}
                    onToggle={() =>
                      setSelectedAccounts((prev) =>
                        prev.includes(key)
                          ? prev.filter((k) => k !== key)
                          : [...prev, key]
                      )
                    }
                    showForward7d={showForward7d}
                    showForward30d={showForward30d}
                  />
                </div>
              );
            })}
          </div>
        </section>
        <section className="rounded-lg border border-gray-800 bg-gray-900/70 p-4 md:p-6">
          <Suspense fallback={<PortfolioDashboardSkeleton />}>
            <PerformanceDashboard owner={data.owner} asOf={data.as_of} />
          </Suspense>
        </section>
      </div>
    </div>
  );
}
