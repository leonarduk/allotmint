import { describe, expect, it } from 'vitest';
import {
  fitPieLabelText,
  layoutPieLabels,
  pieSliceMidAngles,
  type PieLabelGeometry,
  type PieLabelPlacement,
} from '../../../src/lib/pieLabelLayout';

const geometry: PieLabelGeometry = {
  cx: 320,
  cy: 200,
  radius: 100,
  width: 640,
  height: 400,
  lineHeight: 15,
};

const visible = (placements: PieLabelPlacement[]) =>
  placements.filter((p) => p.visible);

/** Every pair of visible labels on one side is at least a line height apart. */
const expectNoOverlap = (
  placements: PieLabelPlacement[],
  lineHeight: number
) => {
  for (const side of ['left', 'right'] as const) {
    const ys = visible(placements)
      .filter((p) => p.side === side)
      .map((p) => p.y)
      .sort((a, b) => a - b);
    for (let i = 1; i < ys.length; i += 1) {
      expect(ys[i] - ys[i - 1]).toBeGreaterThanOrEqual(lineHeight - 1e-6);
    }
  }
};

describe('pieSliceMidAngles (#10313)', () => {
  it('matches recharts default angles: 0° start, counter-clockwise, no padding', () => {
    expect(pieSliceMidAngles([1, 1, 2])).toEqual([
      { midAngle: 45, fraction: 0.25 },
      { midAngle: 135, fraction: 0.25 },
      { midAngle: 270, fraction: 0.5 },
    ]);
  });

  it('treats non-finite values as zero and handles an empty total', () => {
    expect(pieSliceMidAngles([Number.NaN, 2]).map((s) => s.fraction)).toEqual([
      0, 1,
    ]);
    expect(pieSliceMidAngles([0, 0]).map((s) => s.fraction)).toEqual([0, 0]);
  });
});

describe('layoutPieLabels (#10313)', () => {
  it('leaves well-separated labels at their recharts anchors', () => {
    const placements = layoutPieLabels(
      [
        { midAngle: 0, fraction: 0.5 },
        { midAngle: 180, fraction: 0.5 },
      ],
      geometry
    );
    expect(placements[0]).toMatchObject({
      visible: true,
      side: 'right',
      y: 200,
    });
    expect(placements[0].x).toBeCloseTo(420);
    expect(placements[1]).toMatchObject({
      visible: true,
      side: 'left',
      y: 200,
    });
    expect(placements[1].x).toBeCloseTo(220);
  });

  it('nudges the smaller of two colliding labels on the same side, keeping the larger in place', () => {
    // 4° apart near 3 o'clock: anchors ~7px apart vertically.
    const placements = layoutPieLabels(
      [
        { midAngle: 2, fraction: 0.06 },
        { midAngle: 6, fraction: 0.3 },
      ],
      geometry
    );
    const big = placements[1];
    const small = placements[0];
    expect(big.y).toBeCloseTo(200 - Math.sin((6 * Math.PI) / 180) * 100);
    expect(small.visible).toBe(true);
    expect(Math.abs(small.y - big.y)).toBeCloseTo(15);
    expectNoOverlap(placements, 15);
  });

  it('hides a label when no free spot is within the nudge limit', () => {
    const placements = layoutPieLabels(
      [
        { midAngle: 0, fraction: 0.3 },
        { midAngle: 3, fraction: 0.2 },
        { midAngle: -3, fraction: 0.2 },
        { midAngle: 1, fraction: 0.06 },
      ],
      { ...geometry, maxNudge: 15 }
    );
    expect(placements.map((p) => p.visible)).toEqual([true, true, true, false]);
    expectNoOverlap(placements, 15);
  });

  it('does not treat labels on opposite sides as colliding', () => {
    // 88° and 92° straddle 12 o'clock: same height, but they grow away from each other.
    const placements = layoutPieLabels(
      [
        { midAngle: 88, fraction: 0.1 },
        { midAngle: 92, fraction: 0.1 },
      ],
      geometry
    );
    expect(placements.map((p) => [p.visible, p.side])).toEqual([
      [true, 'right'],
      [true, 'left'],
    ]);
    expect(placements[0].y).toBeCloseTo(placements[1].y);
  });

  it('keeps labels inside the container vertically', () => {
    // The anchor of a 12 o'clock slice sits above a short container.
    const placements = layoutPieLabels([{ midAngle: 90, fraction: 1 }], {
      ...geometry,
      cy: 100,
      height: 200,
      radius: 110,
    });
    expect(placements[0].visible).toBe(true);
    expect(placements[0].y).toBe(4 + 7.5);
  });

  it('places many tiny slices without overlap, hiding the ones that do not fit', () => {
    const slices = pieSliceMidAngles(Array.from({ length: 40 }, () => 1));
    const placements = layoutPieLabels(slices, geometry);
    const shown = visible(placements);
    expect(shown.length).toBeGreaterThan(0);
    expect(shown.length).toBeLessThan(40);
    expectNoOverlap(placements, 15);
    for (const p of shown) {
      expect(p.y).toBeGreaterThanOrEqual(4 + 7.5);
      expect(p.y).toBeLessThanOrEqual(400 - 4 - 7.5);
    }
  });

  it('hides slices below minFraction and empty slices', () => {
    const placements = layoutPieLabels(
      [
        { midAngle: 10, fraction: 0.04 },
        { midAngle: 100, fraction: 0 },
        { midAngle: 200, fraction: 0.96 },
      ],
      { ...geometry, minFraction: 0.05 }
    );
    expect(placements.map((p) => p.visible)).toEqual([false, false, true]);
  });
});

describe('fitPieLabelText (#10313)', () => {
  const options = { width: 200, charWidth: 10 };

  it('returns the text unchanged when it fits before the edge', () => {
    expect(
      fitPieLabelText('Cash 37%', { x: 100, side: 'right' }, options)
    ).toBe('Cash 37%');
    expect(fitPieLabelText('Cash 37%', { x: 100, side: 'left' }, options)).toBe(
      'Cash 37%'
    );
  });

  it('truncates text that would run past the right or left edge', () => {
    // Right: 200 - 4 - 100 = 96px -> 9 chars, 8 kept plus the ellipsis.
    expect(
      fitPieLabelText(
        'Investment Trust 31.76%',
        { x: 100, side: 'right' },
        options
      )
    ).toBe('Investme…');
    // Left: 60 - 4 = 56px -> 5 chars, 4 kept plus the ellipsis.
    expect(
      fitPieLabelText('Investment Trust', { x: 60, side: 'left' }, options)
    ).toBe('Inve…');
  });

  it('hides a label when fewer than minChars characters would fit', () => {
    expect(
      fitPieLabelText('Investment Trust', { x: 170, side: 'right' }, options)
    ).toBeNull();
    expect(
      fitPieLabelText('Investment Trust', { x: 2, side: 'left' }, options)
    ).toBeNull();
  });
});
