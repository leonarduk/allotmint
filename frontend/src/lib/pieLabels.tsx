import type { PieLabelRenderProps } from "recharts";
import {
  fitPieLabelText,
  layoutPieLabels,
  pieSliceMidAngles,
  type PieLabelPlacement,
} from "./pieLabelLayout";
import {
  CollisionAwarePieLabel,
  CollisionAwarePieLabelLine,
  type ChartBounds,
  type LabelResolver,
  type PieLabelLineProps,
  type SliceGeometryProps,
} from "./pieLabelElements";

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

/** Font size of collision-aware inline labels; fixed so text width can be estimated. */
export const INLINE_PIE_LABEL_FONT_SIZE = 12;
/** Conservative average glyph width (0.6em) used to estimate label text width. */
export const INLINE_PIE_LABEL_CHAR_WIDTH = INLINE_PIE_LABEL_FONT_SIZE * 0.6;
/** Vertical space reserved per label; closer labels on one side are nudged or hidden. */
export const INLINE_PIE_LABEL_LINE_HEIGHT = Math.ceil(INLINE_PIE_LABEL_FONT_SIZE * 1.25);
/** recharts' default distance between the pie edge and the label anchor. */
const RECHARTS_LABEL_OFFSET = 20;

/**
 * Collision-aware `label` / `labelLine` renderers for one recharts `<Pie>` (#10313).
 *
 * `values` must be the pie's values in data order (what `dataKey` reads), so
 * every slice's label is placed with knowledge of its neighbours. Labels
 * below {@link MIN_INLINE_PIE_LABEL_FRACTION} stay hidden (#7630); colliding
 * labels are nudged or hidden, and long labels are truncated at the container
 * edge. The Legend and Tooltip remain the full identification path for any
 * hidden or truncated label.
 *
 * The container is the chart's actual width × height, read from the recharts
 * chart context (#11181), so an off-centre pie or asymmetric chart margins are
 * fitted against the real edges rather than an assumed `2·cx × 2·cy`.
 */
export function createPieLabelRenderers(
  values: ReadonlyArray<number>,
  format: (props: PieLabelRenderProps) => string,
) {
  const slices = pieSliceMidAngles(values);
  let cache: { key: string; placements: PieLabelPlacement[] } | null = null;

  const placementsFor = (
    cx: number,
    cy: number,
    outerRadius: number,
    bounds: ChartBounds,
  ) => {
    const key = `${cx}|${cy}|${outerRadius}|${bounds.width}|${bounds.height}`;
    if (cache?.key !== key) {
      const placements = layoutPieLabels(slices, {
        cx,
        cy,
        radius: outerRadius + RECHARTS_LABEL_OFFSET,
        width: bounds.width,
        height: bounds.height,
        lineHeight: INLINE_PIE_LABEL_LINE_HEIGHT,
        minFraction: MIN_INLINE_PIE_LABEL_FRACTION,
      });
      cache = { key, placements };
    }
    return cache.placements;
  };

  const resolve: LabelResolver = (props, bounds) => {
    const { cx, cy, outerRadius, index } = props;
    if (!bounds || cx == null || cy == null || outerRadius == null || index == null) {
      return null;
    }
    const placement = placementsFor(cx, cy, outerRadius, bounds)[index];
    if (!placement?.visible) return null;
    const text = fitPieLabelText(format(props as PieLabelRenderProps), placement, {
      width: bounds.width,
      charWidth: INLINE_PIE_LABEL_CHAR_WIDTH,
    });
    return text === null ? null : { placement, text };
  };

  const label = (props: PieLabelRenderProps) => (
    <CollisionAwarePieLabel
      sliceProps={props}
      resolve={resolve}
      fontSize={INLINE_PIE_LABEL_FONT_SIZE}
    />
  );

  const labelLine = (props: PieLabelLineProps & SliceGeometryProps) => (
    <CollisionAwarePieLabelLine sliceProps={props} resolve={resolve} />
  );

  return { label, labelLine };
}
