import type { PieLabelRenderProps } from "recharts";

/**
 * Slices below this share of the pie (as a 0–1 fraction) get no inline label
 * or leader line. Adjacent sub-2% slices otherwise stack their labels in the
 * same few pixels at every chart width (#7630); the Legend and Tooltip still
 * identify those slices.
 */
export const MIN_INLINE_PIE_LABEL_FRACTION = 0.05;

export function isPieSliceLabelable(fraction: number | undefined): boolean {
  return (fraction ?? 0) >= MIN_INLINE_PIE_LABEL_FRACTION;
}

type PieLabelLineProps = {
  percent?: number;
  points?: ReadonlyArray<{ x: number; y: number }>;
  stroke?: string;
};

/** `labelLine` renderer that draws the leader line only for labelable slices. */
export function renderPieLabelLine(props: PieLabelLineProps) {
  const { percent, points, stroke } = props;
  if (!isPieSliceLabelable(percent) || !points || points.length < 2) {
    return <g />;
  }
  return (
    <polyline
      className="recharts-pie-label-line"
      points={points.map((p) => `${p.x},${p.y}`).join(" ")}
      fill="none"
      stroke={stroke}
    />
  );
}

/**
 * Wraps a label formatter so slices below the threshold render nothing.
 * Returning a React element short-circuits recharts' default <Text> wrapper.
 */
export function withSmallSliceLabelsHidden(
  format: (props: PieLabelRenderProps) => string,
) {
  return (props: PieLabelRenderProps) =>
    isPieSliceLabelable(props.percent) ? format(props) : <g />;
}
