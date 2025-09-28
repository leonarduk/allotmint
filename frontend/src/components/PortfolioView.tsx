import { Suspense, useState, useEffect } from "react";
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
};

/**
 * Render a portfolio tree showing an owner's accounts and holdings.
 *
 * The component is intentionally tiny: it deals only with presentation and
 * relies on its parent for data fetching. Conditional branches early-return to
 * keep the JSX at the bottom easy to follow.
 */
export function PortfolioView({ data, loading, error }: Props) {
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);
  const [hasWarnings, setHasWarnings] = useState(false);
  const { baseCurrency } = useConfig();

  const accountKey = (acct: Account, idx: number) => `${acct.account_type}-${idx}`;

  useEffect(() => {
    setSelectedAccounts(data ? data.accounts.map(accountKey) : []);
  }, [data]);

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

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section className="rounded-lg border border-gray-800 bg-gray-900/70 p-4 md:p-6">
          <div className="mb-4 text-sm text-gray-300">
            As of {formatDateISO(new Date(data.as_of))}
          </div>
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
                  />
                </div>
              );
            })}
          </div>
        </section>
        <section className="rounded-lg border border-gray-800 bg-gray-900/70 p-4 md:p-6">
          <Suspense fallback={<PortfolioDashboardSkeleton />}>
            <PerformanceDashboard owner={data.owner} />
          </Suspense>
        </section>
      </div>
    </div>
  );
}
