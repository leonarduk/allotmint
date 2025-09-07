import { useMemo } from "react";
import {
  useInstrumentHistory,
  getCachedInstrumentHistory,
} from "../hooks/useInstrumentHistory";

type SparklineBaseProps = {
  width?: number;
  height?: number;
  color?: string;
  ariaLabel?: string;
  tabIndex?: number;
};

type SparklineDataProps = SparklineBaseProps & {
  data: number[] | { price: number }[];
  ticker?: never;
  days?: never;
};

type SparklineFetchProps = SparklineBaseProps & {
  ticker: string;
  days: number;
  data?: never;
};

type SparklineProps = SparklineDataProps | SparklineFetchProps;

function SparklineSvg({
  series,
  width = 100,
  height = 20,
  color = "#8884d8",
  ariaLabel = "Price trend",
  tabIndex = 0,
}: {
  series: number[];
} & Required<Pick<SparklineBaseProps, "width" | "height" | "color" | "ariaLabel" | "tabIndex">>) {
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
    return (
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={ariaLabel}
        tabIndex={tabIndex}
        data-testid="sparkline-empty"
      />
    );
  }

  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label={ariaLabel}
      tabIndex={tabIndex}
      data-testid="sparkline"
    >
      <polyline points={pointsAttr} fill="none" stroke={color} />
    </svg>
  );
}

function SparklineFromData({
  data,
  width,
  height,
  color,
  ariaLabel,
  tabIndex,
}: SparklineDataProps) {
  const series =
    (data as any[])?.map((d) =>
      typeof d === "number" ? d : (d?.price as number),
    ).filter((v) => typeof v === "number" && Number.isFinite(v)) ?? [];

  return (
    <SparklineSvg
      series={series}
      width={width ?? 100}
      height={height ?? 20}
      color={color ?? "#8884d8"}
      ariaLabel={ariaLabel ?? "Price trend"}
      tabIndex={tabIndex ?? 0}
    />
  );
}

function SparklineFromFetch({
  ticker,
  days,
  width,
  height,
  color,
  ariaLabel,
  tabIndex,
}: SparklineFetchProps) {
  const { data, error } = useInstrumentHistory(ticker, days);
  const cached = getCachedInstrumentHistory(ticker, days);
  const points = (cached ?? data)?.[String(days)] ?? [];
  const series =
    points
      .map(
        (p: any) =>
          (p.close_gbp ?? p.close ?? p.price) as number | undefined,
      )
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v)) ??
    [];

  if (error) {
    return (
      <SparklineSvg
        series={[]}
        width={width ?? 100}
        height={height ?? 20}
        color={color ?? "#8884d8"}
        ariaLabel={ariaLabel ?? `Price trend for ${ticker}`}
        tabIndex={tabIndex ?? 0}
      />
    );
  }

  return (
    <SparklineSvg
      series={series}
      width={width ?? 100}
      height={height ?? 20}
      color={color ?? "#8884d8"}
      ariaLabel={ariaLabel ?? `Price trend for ${ticker}`}
      tabIndex={tabIndex ?? 0}
    />
  );
}

/**
 * Sparkline
 * - Use <Sparkline data={[...]} /> to render from a numeric series (or [{price}]).
 * - Or <Sparkline ticker="VWRL.L" days={90} /> to fetch and render history.
 * - Accessible with role="img" and aria-label.
 * - No external charting libs; lightweight SVG for easy testing.
 */
export function Sparkline(props: SparklineProps) {
  if ("data" in props) {
    return <SparklineFromData {...(props as SparklineDataProps)} />;
  }
  return <SparklineFromFetch {...(props as SparklineFetchProps)} />;
}

export default Sparkline;
