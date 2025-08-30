import { useEffect, useCallback, memo } from "react";
import type { ChangeEventHandler } from "react";
import type { GroupSummary } from "../types";
import { Selector } from "./Selector";

type Props = {
  groups: GroupSummary[];
  selected: string;
  onSelect: (slug: string) => void;
};

export const GroupSelector = memo(function GroupSelector({
  groups,
  selected,
  onSelect,
}: Props) {
  // Auto-select first group if none selected yet
  useEffect(() => {
    if (!selected && groups.length > 0) {
      onSelect(groups[0].slug);
    }
  }, [selected, groups, onSelect]);

  const handleChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (e) => onSelect(e.target.value),
    [onSelect],
  );

  return (
    <Selector
      label="Group"
      value={selected}
      onChange={handleChange}
      options={groups.map((g) => ({ value: g.slug, label: g.name }))}
    />
  );
});
