/* ------------------------------------------------------------------
 *  AccountBlock.tsx   ─ merged, consolidated version
 * ------------------------------------------------------------------ */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Account } from "../types";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { formatDateISO } from "../lib/date";
import {
  useReportingCurrency,
  type ReportingCurrency,
} from "../hooks/useReportingCurrency";

/* ──────────────────────────────────────────────────────────────
 * Component
 * ────────────────────────────────────────────────────────────── */
type Props = {
  account: Account;
  selected?: boolean;
  onToggle?: () => void;
  showForward7d?: boolean;
  showForward30d?: boolean;
  onAddPosition?: () => void;
};


/**
 * A GBP amount, compact, in the reporting currency (#9768). Takes no source
 * currency: ``value_estimate_gbp`` is GBP by name and contract, so labelling
 * it with any other currency would mislabel it (#9805).
 */
function compactGbpValue(value: number, reporting: ReportingCurrency): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: reporting.currency,
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(reporting.convertGbp(value));
}

export function AccountBlock({
  account,
  selected = true,
  onToggle,
  showForward7d = false,
  showForward30d = false,
  onAddPosition,
}: Props) {
  const [selectedInstrument, setSelectedInstrument] = useState<{
    ticker: string;
    name: string;
    instrumentType?: string | null;
  } | null>(null);
  const reporting = useReportingCurrency();
  const { t } = useTranslation();

  return (
    <div className="mb-4 min-w-0 p-2 md:mb-8 md:p-4">
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
            {t("accountBlock.estValue")}
            {account.value_estimate_gbp != null
              ? compactGbpValue(account.value_estimate_gbp, reporting)
              : "—"}
          </div>

          {account.last_updated && (
            <div className="text-muted">
              {t("accountBlock.lastUpdated")}
              {formatDateISO(new Date(account.last_updated))}
            </div>
          )}

          <HoldingsTable
            holdings={account.holdings}
            onSelectInstrument={(ticker, name, instrumentType) =>
              setSelectedInstrument({ ticker, name, instrumentType })
            }
            showForward7d={showForward7d}
            showForward30d={showForward30d}
            onAddPosition={onAddPosition}
          />

          {selectedInstrument && (
            <InstrumentDetail
              ticker={selectedInstrument.ticker}
              name={selectedInstrument.name}
              instrument_type={selectedInstrument.instrumentType}
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
