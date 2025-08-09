import { getCompliance } from "../api";
import type { ComplianceResult } from "../types";
import { useFetch } from "../hooks/useFetch";

interface Props {
  owners: string[];
}

export function ComplianceWarnings({ owners }: Props) {
  const { data } = useFetch<Record<string, string[]>>(
    async () => {
      const entries: Record<string, string[]> = {};
      await Promise.all(
        owners.map(async (o) => {
          try {
            const res: ComplianceResult = await getCompliance(o);
            entries[o] = res.warnings ?? [];
          } catch {
            entries[o] = ["Failed to load warnings"];
          }
        })
      );
      return entries;
    },
    [owners],
    owners.length > 0
  );

  if (!owners.length) return null;

  const ownersWithWarnings = owners.filter((o) => (data?.[o] ?? []).length);

  if (!ownersWithWarnings.length) return null;

  return (
    <div
      style={{
        background: "#fff4e5",
        border: "1px solid #f0ad4e",
        color: "#333",
        padding: "0.5rem 1rem",
        marginBottom: "1rem",
      }}
    >
      {ownersWithWarnings.map((o) => (
        <div key={o} style={{ marginBottom: "0.5rem" }}>
          <strong>{o}</strong>
          <ul style={{ margin: "0.25rem 0 0 1.25rem" }}>
            {(data?.[o] ?? []).map((w) => (
              <li key={`${o}-${w}`}>{w}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
