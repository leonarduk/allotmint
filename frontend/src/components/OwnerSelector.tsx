import type { OwnerSummary } from "../types";
import { Selector } from "./Selector";

type Props = {
  owners: OwnerSummary[];
  selected: string;
  onSelect: (owner: string) => void;
};

export function OwnerSelector({ owners, selected, onSelect }: Props) {
  return (
    <Selector
      label="Owner"
      value={selected}
      onChange={onSelect}
      options={owners.map((o) => ({ value: o.owner, label: o.owner }))}
    />
  );
}

