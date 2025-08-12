/* ------------------------------------------------------------------
 *  AccountBlock.tsx   ─ merged, consolidated version
 * ------------------------------------------------------------------ */

import { useState } from "react";
import type { Account, SelectedInstrument } from "../types";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { money } from "../lib/money";
import i18n from "../i18n";

/* ──────────────────────────────────────────────────────────────
 * Component
 * ────────────────────────────────────────────────────────────── */
type Props = {
  account: Account;
  selected?: boolean;
  onToggle?: () => void;
};

export function AccountBlock({
  account,
  selected = true,
  onToggle,
}: Props) {
  const [selectedInstrument, setSelectedInstrument] =
    useState<SelectedInstrument | null>(null);

  return (
    <div
      style={{
        marginBottom: "2rem",
        padding: "1rem",
      }}
    >
      <h2 style={{ marginTop: 0 }}>
        {onToggle && (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            aria-label={account.account_type}
            style={{ marginRight: "0.5rem" }}
          />
        )}
        {account.account_type} ({account.currency})
      </h2>

      {selected && (
        <>
          <div style={{ marginBottom: "0.5rem" }}>
            Est&nbsp;Value:&nbsp;{money(account.value_estimate_gbp)}
          </div>

          {account.last_updated && (
            <div style={{ fontSize: "0.8rem", color: "#666" }}>
              Last updated:&nbsp;
              {new Intl.DateTimeFormat(i18n.language).format(
                new Date(account.last_updated),
              )}
            </div>
          )}

          <HoldingsTable
            holdings={account.holdings}
            onSelectInstrument={(instrument) => setSelectedInstrument(instrument)}
          />

          {selectedInstrument && (
            <InstrumentDetail
              ticker={selectedInstrument.ticker}
              name={selectedInstrument.name}
              currency={selectedInstrument.currency}
              instrument_type={selectedInstrument.instrument_type}
              onClose={() => setSelectedInstrument(null)}
            />
          )}
        </>
      )}
    </div>
  );
}

/* Export default as convenience for `lazy()` / Storybook */
export default AccountBlock;
