import { ResponsiveContainer, LineChart, Line, YAxis } from "recharts";
import { useInstrumentHistory } from "../hooks/useInstrumentHistory";
import type { InstrumentSummary } from "../types";

interface Props {
  instrument: InstrumentSummary;
  days?: number;
}

export function InstrumentTile({ instrument, days = 30 }: Props) {
  const { data } = useInstrumentHistory(instrument.ticker, days);
  const points = (data?.mini?.[String(days)] ?? []).map((p: any) => ({
    price: p.close_gbp ?? p.close ?? p.price,
  }));

  return (
    <div
      style={{
        border: "1px solid #ccc",
        borderRadius: 4,
        padding: 8,
        boxSizing: "border-box",
        width: "100%",
        height: "100%",
      }}
    >
      <div style={{ fontWeight: 600 }}>{instrument.ticker}</div>
      <div style={{ fontSize: 12, marginBottom: 4 }}>{instrument.name}</div>
      <div style={{ width: "100%", height: 80 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points}>
            <YAxis domain={["auto", "auto"]} hide />
            <Line type="monotone" dataKey="price" stroke="#8884d8" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default InstrumentTile;
