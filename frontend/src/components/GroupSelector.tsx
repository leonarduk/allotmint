import { useEffect } from "react";
import type { GroupSummary } from "../types";

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
    <div style={{ marginBottom: "1rem" }}>
      <label style={{ marginRight: "0.5rem" }}>Group:</label>
      <select
        value={selected}
        onChange={(e) => onSelect(e.target.value)}
      >
        {groups.map((g) => (
          <option key={g.slug} value={g.slug}>
            {g.name}
          </option>
        ))}
      </select>
    </div>
  );
}
