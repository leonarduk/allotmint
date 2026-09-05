import { useCallback } from "react";
import { getCompliance } from "../api";
import type { ComplianceResult } from "../types";
import { useFetch } from "../hooks/useFetch";
import { useConfig } from "../ConfigContext";

interface Props {
  owners: string[];
}

export function ComplianceWarnings({ owners }: Props) {
  const { tabs, disabledTabs } = useConfig();
  const complianceEnabled =
    tabs["trade-compliance"] && !(disabledTabs ?? []).includes("trade-compliance");

  const fetchCompliance = useCallback(async () => {
    const entries = new Map<string, ComplianceResult>();
    await Promise.all(
      owners.map(async (o) => {
        try {
          entries.set(o, await getCompliance(o));
        } catch {
          // A fetch failure here almost always means the compliance route
          // 402'd (allotmint-pro not installed) rather than a real warning,
          // so drop the owner instead of manufacturing a fake warning entry.
        }
      })
    );
    return Object.fromEntries(entries) as Record<string, ComplianceResult>;
  }, [owners]);

  const { data, loading, error } = useFetch<Record<string, ComplianceResult>>(
    fetchCompliance,
    [owners],
    complianceEnabled && owners.length > 0,
    // One `/compliance/{owner}` call per owner, re-fanned out on every mount of
    // the overview. Keyed on the owner set, which is what `fetchCompliance`
    // varies on.
    { cacheKey: `compliance:${[...owners].sort().join(",")}` }
  );

  if (!complianceEnabled || !owners.length || loading || error) return null;

  const ownersWithWarnings = owners.filter(
    (o) => (data?.[o]?.warnings ?? []).length,
  );

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
            {(data?.[o]?.warnings ?? []).map((w) => (
              <li key={`${o}-${w}`}>{w}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
