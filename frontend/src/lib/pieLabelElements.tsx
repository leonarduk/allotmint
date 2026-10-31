import {
  useChartHeight,
  useChartWidth,
  type PieLabelRenderProps,
} from 'recharts';
import type { PieLabelPlacement } from './pieLabelLayout';

/** Slice geometry recharts passes to `label` / `labelLine` renderers. */
export type SliceGeometryProps = {
  cx?: number;
  cy?: number;
  outerRadius?: number;
  index?: number;
};

export type PieLabelLineProps = {
  percent?: number;
  points?: ReadonlyArray<{ x: number; y: number }>;
  stroke?: string;
};

/** Area the labels must stay inside, in SVG pixels from the chart's top-left corner. */
export type ChartBounds = { width: number; height: number };

export type ResolvedLabel = { placement: PieLabelPlacement; text: string };

export type LabelResolver = (
  props: SliceGeometryProps,
  bounds: ChartBounds | null
) => ResolvedLabel | null;

/**
 * The chart's real width × height (#11181). Labels may sit in the chart
 * margins, so the edge that clips them is the chart's SVG, not its plot area.
 * Outside a recharts chart this falls back to `2·cx × 2·cy`, which matches a
 * pie centred in a chart with symmetric margins.
 */
function useChartBounds(props: SliceGeometryProps): ChartBounds | null {
  const chartWidth = useChartWidth();
  const chartHeight = useChartHeight();
  const { cx, cy } = props;
  if (cx == null || cy == null) return null;
  return { width: chartWidth ?? cx * 2, height: chartHeight ?? cy * 2 };
}

/** Inline label text for one slice, placed by `resolve` against the real chart size. */
export function CollisionAwarePieLabel({
  sliceProps,
  resolve,
  fontSize,
}: {
  sliceProps: PieLabelRenderProps;
  resolve: LabelResolver;
  fontSize: number;
}) {
  const resolved = resolve(sliceProps, useChartBounds(sliceProps));
  if (!resolved) return <g />;
  const { placement, text } = resolved;
  return (
    <text
      className="recharts-pie-label-text"
      x={placement.x}
      y={placement.y}
      textAnchor={placement.side === 'right' ? 'start' : 'end'}
      dominantBaseline="central"
      fontSize={fontSize}
      fill={sliceProps.fill}
    >
      {text}
    </text>
  );
}

/** Leader line from the slice edge to wherever `resolve` placed its label; none when hidden. */
export function CollisionAwarePieLabelLine({
  sliceProps,
  resolve,
}: {
  sliceProps: PieLabelLineProps & SliceGeometryProps;
  resolve: LabelResolver;
}) {
  const resolved = resolve(sliceProps, useChartBounds(sliceProps));
  const start = sliceProps.points?.[0];
  if (!resolved || !start) return <g />;
  const end = resolved.placement;
  return (
    <polyline
      className="recharts-pie-label-line"
      points={`${start.x},${start.y} ${end.x},${end.y}`}
      fill="none"
      stroke={sliceProps.stroke}
    />
  );
}
