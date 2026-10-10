import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { getCompliance } from "../api";
import type { ComplianceResult } from "../types";
import { useFetch } from "../hooks/useFetch";
import { useConfig } from "../ConfigContext";

interface Props {
  owners: string[];
}

// Holds the signature of the last warning set the user dismissed. A new or
// changed warning produces a different signature, so the banner comes back.
export const DISMISSED_STORAGE_KEY = "complianceWarningsDismissed";

function readDismissed(): string | null {
  try {
    return window.localStorage.getItem(DISMISSED_STORAGE_KEY);
  } catch (err) {
    console.warn("Unable to read dismissed compliance warnings", err);
    return null;
  }
}

function writeDismissed(signature: string) {
  try {
    window.localStorage.setItem(DISMISSED_STORAGE_KEY, signature);
  } catch (err) {
    // Dismissal still applies for this session via component state.
    console.warn("Unable to persist dismissed compliance warnings", err);
  }
}

export function ComplianceWarnings({ owners }: Props) {
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const [dismissed, setDismissed] = useState<string | null>(readDismissed);
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

  const signature = JSON.stringify(
    [...ownersWithWarnings].sort().map((o) => [o, data?.[o]?.warnings ?? []]),
  );
  if (dismissed === signature) return null;

  const dismiss = () => {
    writeDismissed(signature);
    setDismissed(signature);
  };

  return (
    <div
      role="region"
      aria-label={t("complianceWarnings.title")}
      style={{
        position: "relative",
        background: "#fff4e5",
        border: "1px solid #f0ad4e",
        color: "#333",
        padding: "0.5rem 2.5rem 0.5rem 1rem",
        marginBottom: "1rem",
      }}
    >
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("complianceWarnings.dismiss")}
        title={t("complianceWarnings.dismiss")}
        style={{
          position: "absolute",
          top: "0.25rem",
          right: "0.5rem",
          background: "none",
          border: "none",
          color: "#333",
          fontSize: "1.25rem",
          lineHeight: 1,
          cursor: "pointer",
        }}
      >
        ×
      </button>
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
