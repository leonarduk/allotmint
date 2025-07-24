import type { OwnerSummary } from "../types";

type Props = {
  owners: OwnerSummary[];
  selected: string;
  onSelect: (owner: string) => void;
};

export function OwnerSelector({ owners, selected, onSelect }: Props) {
  return (
    <div style={{ marginBottom: "1rem" }}>
      <label style={{ marginRight: "0.5rem" }}>Owner:</label>
      <select value={selected} onChange={(e) => onSelect(e.target.value)}>
        {owners.map((o) => (
          <option key={o.owner} value={o.owner}>
            {o.owner}
          </option>
        ))}
      </select>
    </div>
  );
}

