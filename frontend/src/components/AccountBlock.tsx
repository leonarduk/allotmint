/* ------------------------------------------------------------------
 *  AccountBlock.tsx   ─ merged, consolidated version
 * ------------------------------------------------------------------ */

import { useState } from "react";
import type { Account } from "../types";
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
  const [selectedInstrument, setSelectedInstrument] = useState<{
    ticker: string;
    name: string;
  } | null>(null);

  return (
    <div className="account-block">
      <h2 className="mt-0">
        {onToggle && (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            aria-label={account.account_type}
            className="mr-05"
          />
        )}
        {account.account_type} ({account.currency})
      </h2>

      {selected && (
        <>
          <div className="mb-05">
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
            onSelectInstrument={(ticker, name) =>
              setSelectedInstrument({ ticker, name })
            }
          />

          {selectedInstrument && (
            <InstrumentDetail
              ticker={selectedInstrument.ticker}
              name={selectedInstrument.name}
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
