import type { ChangeEventHandler } from "react";
import { useTranslation } from "react-i18next";
import type { OwnerSummary } from "@/types";
import { Selector } from "@/components/Selector";
import { getOwnerDisplayName } from "@/utils/owners";
import type { TradeSideFilter } from "./transactionTable";

interface TransactionsFiltersProps {
  owner: string;
  account: string;
  start: string;
  end: string;
  owners: OwnerSummary[];
  ownerLookup: Map<string, string>;
  accountOptions: string[];
  ownerLabel: string;
  startLabel: string;
  endLabel: string;
  onOwnerChange: ChangeEventHandler<HTMLSelectElement>;
  onAccountChange: ChangeEventHandler<HTMLSelectElement>;
  onStartChange: ChangeEventHandler<HTMLInputElement>;
  onEndChange: ChangeEventHandler<HTMLInputElement>;
  side: TradeSideFilter;
  onSideChange: ChangeEventHandler<HTMLSelectElement>;
  ownerAccountLocked?: boolean;
}

export function TransactionsFilters({
  owner,
  account,
  start,
  end,
  owners,
  ownerLookup,
  accountOptions,
  ownerLabel,
  startLabel,
  endLabel,
  onOwnerChange,
  onAccountChange,
  onStartChange,
  onEndChange,
  side,
  onSideChange,
  ownerAccountLocked = false,
}: TransactionsFiltersProps) {
  const { t } = useTranslation();
  return (
    <div style={{ marginBottom: "1rem" }}>
      <Selector
        label={ownerLabel}
        value={owner}
        onChange={onOwnerChange}
        options={[
          { value: "", label: t("transactionsFilters.all") },
          ...owners.map((entry) => ({
            value: entry.owner,
            label: getOwnerDisplayName(ownerLookup, entry.owner, entry.owner),
          })),
        ]}
        disabled={ownerAccountLocked}
      />
      <Selector
        label={t("transactionsFilters.account")}
        value={account}
        onChange={onAccountChange}
        options={[
          { value: "", label: t("transactionsFilters.all") },
          ...accountOptions.map((option) => ({ value: option, label: option })),
        ]}
        disabled={ownerAccountLocked}
      />
      <Selector
        label={t("transactionsFilters.side")}
        value={side}
        onChange={onSideChange}
        options={[
          { value: "", label: t("transactionsFilters.all") },
          { value: "BUY", label: t("transactionsFilters.buy") },
          { value: "SELL", label: t("transactionsFilters.sell") },
        ]}
      />
      <label style={{ marginLeft: "0.5rem" }}>
        {startLabel}: <input type="date" value={start} onChange={onStartChange} />
      </label>
      <label style={{ marginLeft: "0.5rem" }}>
        {endLabel}: <input type="date" value={end} onChange={onEndChange} />
      </label>
    </div>
  );
}
