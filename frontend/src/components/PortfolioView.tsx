import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import type { Portfolio, Account } from "../types";
import { AccountBlock } from "./AccountBlock";
import { ValueAtRisk } from "./ValueAtRisk";
import { money } from "../lib/money";
import { useConfig } from "../ConfigContext";
import i18n from "../i18n";
import { complianceForOwner } from "../api";

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

  const { baseCurrency } = useConfig();

  const totalValue = data.accounts.reduce(
    (sum, acct, idx) =>
      activeSet.has(accountKey(acct, idx))
        ? sum + acct.value_estimate_gbp
        : sum,
    0
  );

  return (
    <div>
      <h1 className="mt-0">
        Portfolio: <span data-testid="owner-name">{data.owner}</span>
      </h1>
      <div className="mb-4">
        As of {new Intl.DateTimeFormat(i18n.language).format(new Date(data.as_of))}
      </div>
      <div className="mb-8">
        Approx Total: {money(totalValue, baseCurrency)}
      </div>
        {hasWarnings && (
          <div className="mb-4">
            <Link to={`/compliance/${data.owner}`}>View compliance warnings</Link>
          </div>
        )}
      <ValueAtRisk owner={data.owner} />
      {/* Each account is rendered using AccountBlock for clarity */}
      {data.accounts.map((acct, idx) => {
        const key = accountKey(acct, idx);
        const checked = activeSet.has(key);
        return (
          <AccountBlock
            key={key}
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
        );
      })}
    </div>
  );
}
