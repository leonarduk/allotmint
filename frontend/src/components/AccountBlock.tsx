/* ------------------------------------------------------------------
 *  AccountBlock.tsx   ─ merged, consolidated version
 * ------------------------------------------------------------------ */

import { useState } from "react";
import type { Account } from "../types";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";

/* ──────────────────────────────────────────────────────────────
 * Helpers
 * ────────────────────────────────────────────────────────────── */
const formatGBP = (n: number | undefined) =>
  (n ?? 0).toLocaleString(undefined, {
    style: "currency",
    currency: "GBP",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

/* ──────────────────────────────────────────────────────────────
 * Component
 * ────────────────────────────────────────────────────────────── */
type Props = { account: Account };

export function AccountBlock({ account }: Props) {
  const [selected, setSelected] = useState<{
    ticker: string;
    name: string;
  } | null>(null);

  return (
    <div
      style={{
        marginBottom: "2rem",
        padding: "1rem",
        border: "1px solid #ddd",
        borderRadius: "4px",
      }}
    >
      <h2 style={{ marginTop: 0 }}>
        {account.account_type} ({account.currency})
      </h2>

      <div style={{ marginBottom: "0.5rem" }}>
        Est&nbsp;Value:&nbsp;{formatGBP(account.value_estimate_gbp)}
      </div>

      {account.last_updated && (
        <div style={{ fontSize: "0.8rem", color: "#666" }}>
          Last updated:&nbsp;{account.last_updated}
        </div>
      )}

      <HoldingsTable
        holdings={account.holdings}
        onSelectInstrument={(ticker, name) => setSelected({ ticker, name })}
      />

      {selected && (
        <InstrumentDetail
          ticker={selected.ticker}
          name={selected.name}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

/* Export default as convenience for `lazy()` / Storybook */
export default AccountBlock;
