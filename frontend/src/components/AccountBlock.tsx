/* ------------------------------------------------------------------
 *  AccountBlock.tsx   ─ merged, consolidated version
 * ------------------------------------------------------------------ */

import { useState } from "react";
import type { Account } from "../types";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { money } from "../lib/money";
import { formatDateISO } from "../lib/date";
import { useConfig } from "../ConfigContext";

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
  const { baseCurrency } = useConfig();

  return (
    <div className="mb-4 p-2 md:mb-8 md:p-4">
      <h2 className="mt-0">
        {onToggle && (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            aria-label={account.account_type}
            className="mr-2"
          />
        )}
        {account.account_type} ({account.currency})
      </h2>

      {selected && (
        <>
          <div className="mb-2">
            Est&nbsp;Value:&nbsp;
            {account.value_estimate_gbp != null
              ? new Intl.NumberFormat(undefined, {
                  style: "currency",
                  currency:
                    account.value_estimate_currency || baseCurrency,
                  notation: "compact",
                  maximumFractionDigits: 2,
                }).format(account.value_estimate_gbp)
              : "—"}
          </div>

          {account.last_updated && (
            <div className="text-muted">
              Last updated:&nbsp;
              {formatDateISO(new Date(account.last_updated))}
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
