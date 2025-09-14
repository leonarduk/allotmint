import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  Tooltip,
} from "recharts";
import { getValueAtRisk, getAlerts } from "../api";
import type { Alert } from "../types";

interface RightRailProps {
  owner: string;
}

interface VarDatum {
  horizon: string;
  value: number | null;
}

export default function RightRail({ owner }: RightRailProps) {
  const [varData, setVarData] = useState<VarDatum[]>([]);
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    if (!owner) {
      setVarData([]);
      return;
    }
    Promise.resolve(getValueAtRisk?.(owner, { days: 30 }))
      .then((res) => {
        const d: VarDatum[] = [
          { horizon: "1d", value: res.var["1d"] ?? null },
          { horizon: "10d", value: res.var["10d"] ?? null },
        ];
        setVarData(d.filter((v) => v.value != null));
      })
      .catch(() => setVarData([]));
  }, [owner]);

  useEffect(() => {
    if (typeof getAlerts === "function") {
      Promise.resolve(getAlerts())
        .then((res) => setAlerts(res.slice(0, 3)))
        .catch(() => setAlerts([]));
    }
  }, []);

  const content = (
    <div className="space-y-4">
      <div>
        <h3 className="mb-2 text-lg font-semibold">Value at Risk</h3>
        {varData.length > 0 ? (
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={varData}>
              <XAxis dataKey="horizon" hide />
              <Tooltip />
              <Bar dataKey="value" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-gray-500">No data</p>
        )}
      </div>
      <div>
        <h3 className="mb-2 text-lg font-semibold">Alerts</h3>
        {alerts.length > 0 ? (
          <ul className="list-disc pl-4 text-sm">
            {alerts.map((a, i) => (
              <li key={i}>
                <strong>{a.ticker}</strong>: {a.message}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500">No alerts</p>
        )}
      </div>
      <div className="flex flex-col space-y-1 text-sm">
        <a href="/docs" className="text-blue-600 hover:underline">
          Docs
        </a>
        <a href="/support" className="text-blue-600 hover:underline">
          Help
        </a>
      </div>
    </div>
  );

  return (
    <>
      <aside className="hidden xl:block w-64 p-4" data-testid="right-rail">
        {content}
      </aside>
      <button
        className="fixed bottom-4 right-4 rounded-full bg-blue-600 p-3 text-white shadow-xl xl:hidden"
        aria-label="Open info panel"
        onClick={() => setOpen(true)}
      >
        ☰
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-end xl:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setOpen(false)}
          />
          <div className="relative w-full rounded-t-lg bg-white p-4">
            <button
              className="mb-2 text-sm text-gray-600"
              onClick={() => setOpen(false)}
            >
              Close
            </button>
            {content}
          </div>
        </div>
      )}
    </>
  );
}
