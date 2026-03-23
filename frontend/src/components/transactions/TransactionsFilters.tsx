import type { ChangeEventHandler } from "react";
import type { OwnerSummary } from "@/types";
import { Selector } from "@/components/Selector";
import { getOwnerDisplayName } from "@/utils/owners";

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
}: TransactionsFiltersProps) {
  return (
    <div style={{ marginBottom: "1rem" }}>
      <Selector
        label={ownerLabel}
        value={owner}
        onChange={onOwnerChange}
        options={[
          { value: "", label: "All" },
          ...owners.map((entry) => ({
            value: entry.owner,
            label: getOwnerDisplayName(ownerLookup, entry.owner, entry.owner),
          })),
        ]}
      />
      <Selector
        label="Account"
        value={account}
        onChange={onAccountChange}
        options={[
          { value: "", label: "All" },
          ...accountOptions.map((option) => ({ value: option, label: option })),
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
