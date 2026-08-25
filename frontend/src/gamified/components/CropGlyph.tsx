import { useId } from 'react';
import { cropSpecies } from '../cropGlyph';
import { GLYPH_SHAPES, STAGE_FILL, type CropSpecies } from '../glyphShapes';
import type { GrowthStage } from '../plotModel';

const VIEW_BOX = 48;
/** Stroke weight the shapes were drawn at, in viewBox units. */
const BASE_STROKE = 2.4;

interface CropGlyphProps {
  /** Pass either a species directly, or a ticker/sector to derive one. */
  species?: CropSpecies;
  ticker?: string;
  sector?: string | null;
  stage: GrowthStage;
}

/**
 * One crop, drawn.
 *
 * Colour comes from `currentColor` and the box from `1em`, so a caller sets
 * the stage accent and the size once on a wrapper and the outline, the fill
 * and the glow all follow — including the responsive `clamp()` sizes. The fill is a rect
 * clipped to the silhouette and anchored to the base, so it reads as the crop
 * filling out rather than as a progress bar laid over a picture.
 *
 * Always `aria-hidden`: it decorates a card that already names the ticker and
 * the stage in text, so announcing the plant would add noise, not meaning.
 */
export default function CropGlyph({
  species,
  ticker,
  sector,
  stage,
}: CropGlyphProps) {
  // useId keeps the clip path unique per instance — several glyphs share a
  // document, and a duplicated id would point every fill at the first shape.
  const clipId = `crop-glyph-${useId()}`;
  const resolved = species ?? cropSpecies(ticker ?? '', sector);
  const shape = GLYPH_SHAPES[resolved];
  const fill = STAGE_FILL[stage] ?? 0;
  const fillHeight = VIEW_BOX * fill;

  return (
    <svg
      viewBox={`0 0 ${VIEW_BOX} ${VIEW_BOX}`}
      width="1em"
      height="1em"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <clipPath id={clipId}>
          <path d={shape.body} />
        </clipPath>
      </defs>
      {fill > 0 && (
        <rect
          x={0}
          y={VIEW_BOX - fillHeight}
          width={VIEW_BOX}
          height={fillHeight}
          clipPath={`url(#${clipId})`}
          fill="currentColor"
          opacity={0.3}
        />
      )}
      <path
        d={shape.body}
        fill="none"
        stroke="currentColor"
        strokeWidth={BASE_STROKE}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {shape.details.map((detail) => (
        <path
          key={detail}
          d={detail}
          fill="none"
          stroke="currentColor"
          strokeWidth={BASE_STROKE * 0.82}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
      {shape.dots.map(([cx, cy, r]) => (
        <circle
          key={`${cx}-${cy}`}
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={BASE_STROKE * 0.72}
        />
      ))}
    </svg>
  );
}
