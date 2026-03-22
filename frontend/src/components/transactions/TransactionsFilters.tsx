import { Selector } from "../Selector";
import type { OwnerSummary } from "../../types";
import { getOwnerDisplayName } from "../../utils/owners";

type Props = {
  owners: OwnerSummary[];
  ownerLookup: Map<string, string>;
  owner: string;
  account: string;
  start: string;
  end: string;
  accountOptions: string[];
  ownerLabel: string;
  startLabel: string;
  endLabel: string;
  onOwnerChange: React.ChangeEventHandler<HTMLSelectElement>;
  onAccountChange: React.ChangeEventHandler<HTMLSelectElement>;
  onStartChange: (value: string) => void;
  onEndChange: (value: string) => void;
};

export function TransactionsFilters({
  owners,
  ownerLookup,
  owner,
  account,
  start,
  end,
  accountOptions,
  ownerLabel,
  startLabel,
  endLabel,
  onOwnerChange,
  onAccountChange,
  onStartChange,
  onEndChange,
}: Props) {
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
          ...accountOptions.map((value) => ({ value, label: value })),
        ]}
      />
      <label style={{ marginLeft: "0.5rem" }}>
        {startLabel}: <input type="date" value={start} onChange={(event) => onStartChange(event.target.value)} />
      </label>
      <label style={{ marginLeft: "0.5rem" }}>
        {endLabel}: <input type="date" value={end} onChange={(event) => onEndChange(event.target.value)} />
      </label>
    </div>
  );
}
