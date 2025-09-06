import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip } from "recharts";

export type InstrumentHistoryPoint = {
  date: string;
  close_gbp?: number | null;
  close?: number | null;
  [key: string]: any;
};

interface Props {
  data: InstrumentHistoryPoint[];
  loading?: boolean;
  showBollinger?: boolean;
}

export function InstrumentHistoryChart({ data, loading = false, showBollinger = false }: Props) {
  const { t } = useTranslation();

  const prices = useMemo(() => {
    const raw = data
      .map((p) => ({ date: p.date, close_gbp: (p.close_gbp ?? p.close) as number }))
      .filter((p) => typeof p.close_gbp === "number" && Number.isFinite(p.close_gbp));

    return raw.map((p, i, arr) => {
      const start = Math.max(0, i - 19);
      const slice = arr.slice(start, i + 1);
      const mean = slice.reduce((sum, s) => sum + s.close_gbp, 0) / slice.length;
      const variance = slice.reduce((sum, s) => sum + Math.pow(s.close_gbp - mean, 2), 0) / slice.length;
      const stdDev = Math.sqrt(variance);
      const hasFullWindow = slice.length === 20;
      return {
        ...p,
        bb_mid: hasFullWindow ? mean : NaN,
        bb_upper: hasFullWindow ? mean + 2 * stdDev : NaN,
        bb_lower: hasFullWindow ? mean - 2 * stdDev : NaN,
      };
    });
  }, [data]);

  if (loading) {
    return (
      <div
        style={{
          height: 220,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {t("app.loading")}
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={prices}>
        <XAxis dataKey="date" hide />
        <YAxis domain={["auto", "auto"]} />
        <Tooltip wrapperStyle={{ color: "#000" }} labelStyle={{ color: "#000" }} />
        {showBollinger && (
          <>
            <Line type="monotone" dataKey="bb_upper" stroke="#8884d8" dot={false} strokeDasharray="3 3" />
            <Line type="monotone" dataKey="bb_mid" stroke="#ff7300" dot={false} strokeDasharray="5 5" />
            <Line type="monotone" dataKey="bb_lower" stroke="#8884d8" dot={false} strokeDasharray="3 3" />
          </>
        )}
        <Line type="monotone" dataKey="close_gbp" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default InstrumentHistoryChart;
