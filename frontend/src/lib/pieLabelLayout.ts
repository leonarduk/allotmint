/**
 * Pure, DOM-free placement logic for inline pie-chart labels (#10313).
 *
 * recharts renders each slice label independently at `outerRadius + offset`
 * on the slice's mid-angle, so adjacent small slices can stack labels on top
 * of each other and labels near 0°/180° can run past the chart edge. These
 * helpers look at the whole slice list at once: they nudge or hide colliding
 * labels, keep labels vertically inside the container, and truncate label
 * text that would run past the left/right edge.
 */

/** One pie slice, in recharts' angle convention (degrees, 0° = 3 o'clock, counter-clockwise). */
export type PieLabelSlice = {
  midAngle: number;
  /** Share of the whole pie as a 0–1 fraction. */
  fraction: number;
};

export type PieLabelGeometry = {
  cx: number;
  cy: number;
  /** Radius of the label anchor (recharts: outerRadius + label offset). */
  radius: number;
  /** Container width; labels must stay within [padding, width - padding]. */
  width: number;
  /** Container height; labels must stay within [padding, height - padding]. */
  height: number;
  /** Vertical space one label needs; two labels on one side closer than this overlap. */
  lineHeight: number;
  /** Largest vertical shift allowed to clear a collision; beyond it the label is hidden. Defaults to `lineHeight`. */
  maxNudge?: number;
  /** Gap kept between a label and the container edge. Defaults to 4px. */
  padding?: number;
  /** Slices below this fraction get no label. Defaults to 0 (no size threshold). */
  minFraction?: number;
};

export type PieLabelSide = 'left' | 'right';

export type PieLabelPlacement = {
  visible: boolean;
  /** Anchor point of the label text (text grows away from the pie on `side`). */
  x: number;
  y: number;
  side: PieLabelSide;
};

const RADIAN = Math.PI / 180;
const EPSILON = 1e-6;

/** Mid-angles recharts gives slices of `values` with default start/end angles, padding and minAngle. */
export function pieSliceMidAngles(
  values: ReadonlyArray<number>
): PieLabelSlice[] {
  const clean = values.map((v) =>
    typeof v === 'number' && Number.isFinite(v) ? v : 0
  );
  const sum = clean.reduce((acc, v) => acc + v, 0);
  let start = 0;
  return clean.map((v) => {
    const fraction = sum > 0 ? v / sum : 0;
    const end = start + fraction * 360;
    const slice = { midAngle: (start + end) / 2, fraction };
    start = end;
    return slice;
  });
}

function anchorFor(slice: PieLabelSlice, g: PieLabelGeometry) {
  const x = g.cx + Math.cos(-RADIAN * slice.midAngle) * g.radius;
  const y = g.cy + Math.sin(-RADIAN * slice.midAngle) * g.radius;
  const side: PieLabelSide = x >= g.cx ? 'right' : 'left';
  return { x, y, side };
}

function clamp(value: number, min: number, max: number): number {
  if (max < min) return (min + max) / 2;
  return Math.min(Math.max(value, min), max);
}

function collides(
  y: number,
  others: ReadonlyArray<number>,
  lineHeight: number
): boolean {
  return others.some((other) => Math.abs(other - y) < lineHeight - EPSILON);
}

/** Nearest y (to `desired`) that clears every placed label, or null if none is within reach. */
function resolveY(
  desired: number,
  placed: ReadonlyArray<number>,
  bounds: { min: number; max: number; maxNudge: number; lineHeight: number }
): number | null {
  const { min, max, maxNudge, lineHeight } = bounds;
  const candidates = [
    desired,
    ...placed.flatMap((p) => [p - lineHeight, p + lineHeight]),
  ]
    .filter((y) => y >= min - EPSILON && y <= max + EPSILON)
    .filter((y) => Math.abs(y - desired) <= maxNudge + EPSILON)
    .sort((a, b) => Math.abs(a - desired) - Math.abs(b - desired));
  return candidates.find((y) => !collides(y, placed, lineHeight)) ?? null;
}

/**
 * Place every slice's label at once. Larger slices are placed first so they
 * keep their natural spot; a smaller slice's label is nudged vertically to
 * clear it, or hidden if no free spot is within `maxNudge`. Labels are also
 * clamped vertically inside the container. Returns one placement per slice,
 * in input order.
 */
export function layoutPieLabels(
  slices: ReadonlyArray<PieLabelSlice>,
  geometry: PieLabelGeometry
): PieLabelPlacement[] {
  const padding = geometry.padding ?? 4;
  const half = geometry.lineHeight / 2;
  const bounds = {
    min: padding + half,
    max: geometry.height - padding - half,
    maxNudge: geometry.maxNudge ?? geometry.lineHeight,
    lineHeight: geometry.lineHeight,
  };
  const minFraction = geometry.minFraction ?? 0;
  const placements: PieLabelPlacement[] = slices.map((slice) => ({
    ...anchorFor(slice, geometry),
    visible: false,
  }));
  const placedBySide: Record<PieLabelSide, number[]> = { left: [], right: [] };

  const order = slices
    .map((slice, index) => ({ slice, index }))
    .filter(({ slice }) => slice.fraction > 0 && slice.fraction >= minFraction)
    .sort((a, b) => b.slice.fraction - a.slice.fraction || a.index - b.index);

  for (const { index } of order) {
    const placement = placements[index];
    const desired = clamp(placement.y, bounds.min, bounds.max);
    const placed = placedBySide[placement.side];
    const y = resolveY(desired, placed, bounds);
    if (y === null) continue;
    placed.push(y);
    placements[index] = { ...placement, y, visible: true };
  }
  return placements;
}

export type FitPieLabelTextOptions = {
  /** Container width. */
  width: number;
  /** Estimated width of one character, in px. */
  charWidth: number;
  /** Gap kept between the text and the container edge. Defaults to 4px. */
  padding?: number;
  /** Fewest original characters worth showing before the ellipsis; below this the label is hidden. Defaults to 3. */
  minChars?: number;
};

/**
 * Text that fits between the label anchor and the container edge on its
 * side: the full text, a truncated "…" version, or null when not even
 * `minChars` characters fit.
 */
export function fitPieLabelText(
  text: string,
  placement: Pick<PieLabelPlacement, 'x' | 'side'>,
  options: FitPieLabelTextOptions
): string | null {
  const padding = options.padding ?? 4;
  const minChars = options.minChars ?? 3;
  const available =
    placement.side === 'right'
      ? options.width - padding - placement.x
      : placement.x - padding;
  const maxChars = Math.floor(available / options.charWidth + EPSILON);
  if (text.length <= maxChars) return text;
  // Reserve one character's width for the ellipsis.
  const keep = maxChars - 1;
  if (keep < minChars) return null;
  return `${text.slice(0, keep).trimEnd()}…`;
}
