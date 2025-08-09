/* ------------------------------------------------------------------
 *  AccountBlock.tsx   ─ merged, consolidated version
 * ------------------------------------------------------------------ */

import { useState } from "react";
import type { Account } from "../types";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { money } from "../lib/money";

/* ──────────────────────────────────────────────────────────────
 * Component
 * ────────────────────────────────────────────────────────────── */
type Props = { account: Account; total_value_estimate_gbp: number };

export function AccountBlock({ account, total_value_estimate_gbp }: Props) {
  const [selected, setSelected] = useState<{
    ticker: string;
    name: string;
  } | null>(null);

  return (
    <div
      style={{
        marginBottom: "2rem",
        padding: "1rem",
      }}
    >
      <h2 style={{ marginTop: 0 }}>
        {account.account_type} ({account.currency})
      </h2>

      <div style={{ marginBottom: "0.5rem" }}>
        Est&nbsp;Value:&nbsp;{money(account.value_estimate_gbp)}
      </div>

      {account.last_updated && (
        <div style={{ fontSize: "0.8rem", color: "#666" }}>
          Last updated:&nbsp;{account.last_updated}
        </div>
      )}

      <HoldingsTable
        holdings={account.holdings}
        total_value_estimate_gbp={total_value_estimate_gbp}
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
