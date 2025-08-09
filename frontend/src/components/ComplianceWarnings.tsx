import { useEffect, useState } from "react";
import { getCompliance } from "../api";
import type { ComplianceResult } from "../types";

interface Props {
  owners: string[];
}

export function ComplianceWarnings({ owners }: Props) {
  const [data, setData] = useState<Record<string, string[]>>({});

  useEffect(() => {
    if (!owners.length) {
      setData({});
      return;
    }
    let cancelled = false;
    async function load() {
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
      if (!cancelled) setData(entries);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [owners]);

  if (!owners.length) return null;

  const ownersWithWarnings = owners.filter((o) => (data[o] ?? []).length);

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
            {data[o].map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
