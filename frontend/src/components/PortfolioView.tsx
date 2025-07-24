import type { Portfolio } from "../types";
import { AccountBlock } from "./AccountBlock";

type Props = {
  data: Portfolio | null;
  loading?: boolean;
  error?: string | null;
};

export function PortfolioView({ data, loading, error }: Props) {
  if (loading) return <div>Loading portfolio…</div>;
  if (error) return <div style={{ color: "red" }}>{error}</div>;
  if (!data) return <div>Select an owner.</div>;

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Portfolio: {data.owner}</h1>
      <div style={{ marginBottom: "1rem" }}>
        As of {data.as_of} • Trades this month: {data.trades_this_month} / 20 (Remaining: {data.trades_remaining})
      </div>
      <div style={{ marginBottom: "2rem" }}>
        Approx Total: £{data.total_value_estimate_gbp.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}
      </div>
      {data.accounts.map((acct) => (
        <AccountBlock key={acct.account_type} account={acct} />
      ))}
    </div>
  );
}
