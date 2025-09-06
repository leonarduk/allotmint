import { useEffect, useRef, useState } from "react";
import * as api from "../api";
import type { Alert } from "../types";
import { useVirtualizer } from "@tanstack/react-virtual";
import errorToast from "../utils/errorToast";

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const parentRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error("timeout")), 5000),
    );

    Promise.race([api.getAlerts(), timeout])
      .then((res) => {
        if (!cancelled) setAlerts(res);
      })
      .catch((e) => {
        if (!cancelled) {
          setAlerts([]);
          setError(
            navigator.onLine
              ? "Request timed out. Please try again."
              : "You appear to be offline.",
          );
          errorToast(e);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const rowVirtualizer = useVirtualizer({
    count: alerts.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32,
    overscan: 5,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualRows.length ? virtualRows[0].start : 0;
  const paddingBottom = virtualRows.length
    ? rowVirtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end
    : 0;

  // Fallback items before measurement so we still render something
  const items = virtualRows.length
    ? virtualRows
    : alerts.map((_, index) => ({ index, start: index * 32, end: (index + 1) * 32 }));

  if (loading) {
    return (
      <div role="status" aria-live="polite">
        Loading...
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert" aria-live="assertive">
        {error}
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div role="status" aria-live="polite">
        No alerts.
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      style={{ maxHeight: "60vh", overflowY: "auto", overflowX: "hidden" }}
      aria-live="polite"
    >
      <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
        {paddingTop > 0 && <li style={{ height: paddingTop }} />}
        {items.map((virtualRow) => {
          const a = alerts[virtualRow.index];
          const key = (a as any)?.id ?? `${a.ticker}-${virtualRow.index}`;
          return (
            <li key={key} style={{ height: 32, display: "flex", alignItems: "center" }}>
              <strong>{a.ticker}</strong>: {a.message}
            </li>
          );
        })}
        {paddingBottom > 0 && <li style={{ height: paddingBottom }} />}
      </ul>
    </div>
  );
}
