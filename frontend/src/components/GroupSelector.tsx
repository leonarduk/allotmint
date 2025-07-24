import type { GroupSummary } from "../types";

type Props = {
  groups: GroupSummary[];
  selected: string;
  onSelect: (group: string) => void;
};

export function GroupSelector({ groups, selected, onSelect }: Props) {
  return (
    <div style={{ marginBottom: "1rem" }}>
      <label style={{ marginRight: "0.5rem" }}>Group:</label>
      <select value={selected} onChange={(e) => onSelect(e.target.value)}>
        {groups.map((g) => (
          <option key={g.group} value={g.group}>
            {g.group}
          </option>
        ))}
      </select>
    </div>
  );
}
