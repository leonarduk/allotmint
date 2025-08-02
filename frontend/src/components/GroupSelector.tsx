// src/components/GroupSelector.tsx
import type {GroupSummary} from "../types";

type Props = {
    groups: GroupSummary[];     // array from /groups endpoint
    selected: string;           // currently-selected slug ('' for none)
    onSelect: (slug: string) => void;
};

export function GroupSelector({groups, selected, onSelect}: Props) {
    return (
        <div style={{marginBottom: "1rem"}}>
            <label style={{marginRight: "0.5rem"}}>Group:</label>

            <select
                value={selected}
                onChange={(e) => onSelect(e.target.value)}
            >
                <option value="" disabled>
                    Select a group
                </option>

                {groups.map((g) => (
                    <option key={g.slug} value={g.slug}>
                        {g.name}
                    </option>
                ))}
            </select>
        </div>
    );
}
