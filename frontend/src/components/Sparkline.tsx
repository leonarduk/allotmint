import React from "react";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
}

/**
 * Renders a small SVG sparkline for the provided numeric data.
 *
 * This component is intentionally very small and does not rely on any third
 * party charting libraries which keeps the unit tests simple.
 */
export function Sparkline({ data, width = 100, height = 20 }: SparklineProps) {
  if (data.length === 0) {
    return <svg width={width} height={height} data-testid="sparkline-empty" />;
  }

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((d - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg width={width} height={height} data-testid="sparkline">
      <polyline points={points} fill="none" stroke="currentColor" />
    </svg>
  );
}

export default Sparkline;
