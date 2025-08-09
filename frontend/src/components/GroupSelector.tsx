import { useEffect } from "react";
import type { GroupSummary } from "../types";
import { Selector } from "./Selector";

type Props = {
  groups: GroupSummary[];
  selected: string;
  onSelect: (slug: string) => void;
};

export function GroupSelector({ groups, selected, onSelect }: Props) {
  // Auto-select first group if none selected yet
  useEffect(() => {
    if (!selected && groups.length > 0) {
      onSelect(groups[0].slug);
    }
  }, [selected, groups, onSelect]);

  return (
    <Selector
      label="Group"
      value={selected}
      onChange={onSelect}
      options={groups.map((g) => ({ value: g.slug, label: g.name }))}
    />
  );
}
