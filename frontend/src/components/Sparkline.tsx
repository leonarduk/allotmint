import React, { useMemo } from "react";
import { useInstrumentHistory } from "../hooks/useInstrumentHistory";

type SparklineDataProps = {
  data: number[];
  width?: number;
  height?: number;
};

type SparklineFetchProps = {
  ticker: string;
  days: number;
  width?: number;
  height?: number;
};

type SparklineProps = SparklineDataProps | SparklineFetchProps;

/**
 * Renders a small SVG sparkline.
 * - If `data` is provided, it will render directly from the numeric series.
 * - If `ticker` and `days` are provided, it fetches history and renders close/close_gbp values.
 * Kept dependency-light for simple testing and predictable rendering.
 */
export function Sparkline(props: SparklineProps) {
  const width = props.width ?? 100;
  const height = props.height ?? 20;

  // Build numeric series either from props.data or fetched history
  const series: number[] = ((): number[] => {
    if ("data" in props) return props.data ?? [];

    const { ticker, days } = props;
    const { data } = useInstrumentHistory(ticker, days);
    const points = data?.[String(days)] ?? [];
    return points
      .map((p: any) => (p.close_gbp ?? p.close) as number | undefined)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  })();

  const pointsAttr = useMemo(() => {
    if (series.length === 0) return "";
    const max = Math.max(...series);
    const min = Math.min(...series);
    const range = max - min || 1;

    return series
      .map((d, i) => {
        const x = (i / (series.length - 1)) * width;
        const y = height - ((d - min) / range) * height;
        return `${x},${y}`;
      })
      .join(" ");
  }, [series, width, height]);

  if (series.length === 0) {
    return <svg width={width} height={height} data-testid="sparkline-empty" />;
  }

  return (
    <svg width={width} height={height} data-testid="sparkline">
      <polyline points={pointsAttr} fill="none" stroke="currentColor" />
    </svg>
  );
}

export default Sparkline;
