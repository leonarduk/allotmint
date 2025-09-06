import { useEffect, useRef, useState } from "react";
import * as api from "../api";
import type { Alert } from "../types";
import { useVirtualizer } from "@tanstack/react-virtual";

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const parentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getAlerts()
      .then(setAlerts)
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false));
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
  const items = virtualRows.length
    ? virtualRows
    : alerts.map((_, index) => ({ index, start: index * 32, end: (index + 1) * 32 }));

  if (loading) return <div>Loading...</div>;
  if (alerts.length === 0) return <div>No alerts.</div>;

  return (
    <div
      ref={parentRef}
      style={{ maxHeight: "60vh", overflowY: "auto", overflowX: "hidden" }}
    >
      <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
        {paddingTop > 0 && <li style={{ height: paddingTop }} />}
        {items.map((virtualRow) => {
          const a = alerts[virtualRow.index];
          return (
            <li key={virtualRow.index} style={{ height: 32 }}>
              <strong>{a.ticker}</strong>: {a.message}
            </li>
          );
        })}
        {paddingBottom > 0 && <li style={{ height: paddingBottom }} />}
      </ul>
    </div>
  );
}
