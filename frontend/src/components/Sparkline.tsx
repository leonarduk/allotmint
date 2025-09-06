import { memo, useMemo } from "react";
import { ResponsiveContainer, LineChart, Line } from "recharts";
import { useInstrumentHistory } from "../hooks/useInstrumentHistory";

interface SparklineProps {
  ticker: string;
  days: number;
}

export const Sparkline = memo(function Sparkline({ ticker, days }: SparklineProps) {
  const { data } = useInstrumentHistory(ticker, days);
  const points = data?.[String(days)] ?? [];

  const chartData = useMemo(
    () => points.map((p) => ({ value: p.close_gbp ?? p.close })),
    [points],
  );

  if (chartData.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={30}>
      <LineChart
        data={chartData}
        margin={{ left: 0, right: 0, top: 0, bottom: 0 }}
      >
        <Line type="monotone" dataKey="value" stroke="#8884d8" dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
});
