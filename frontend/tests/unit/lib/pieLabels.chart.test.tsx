import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { Pie, PieChart } from 'recharts';
import {
  INLINE_PIE_LABEL_CHAR_WIDTH,
  INLINE_PIE_LABEL_LINE_HEIGHT,
  createPieLabelRenderers,
  renderPieLabelLine,
  withSmallSliceLabelsHidden,
} from '../../../src/lib/pieLabels';

// The demo allocation from #7630: three adjacent sub-2% slices whose labels
// collided. Rendered through recharts' real <Pie> label pipeline (not just the
// helpers in isolation) so a recharts upgrade that stops honouring an element
// returned from `label`/`labelLine` fails here.
const demoAllocation = [
  { name: 'Cash', value: 36.98 },
  { name: 'ETF', value: 31.76 },
  { name: 'Equity', value: 26.86 },
  { name: 'Fund', value: 1.85 },
  { name: 'Investment Trust', value: 0.9 },
  { name: 'Real Estate', value: 1.65 },
];

describe('pie labels inside a real recharts <Pie> (#7630)', () => {
  it('renders text and leader lines only for slices at or above the threshold', () => {
    const { container } = render(
      <PieChart width={700} height={300}>
        <Pie
          dataKey="value"
          data={demoAllocation}
          isAnimationActive={false}
          labelLine={renderPieLabelLine}
          label={withSmallSliceLabelsHidden((p) => String(p.name))}
        />
      </PieChart>,
    );

    const labelTexts = Array.from(
      container.querySelectorAll('svg text'),
    ).map((node) => node.textContent);
    expect(labelTexts).toEqual(['Cash', 'ETF', 'Equity']);
    expect(container.querySelectorAll('svg polyline')).toHaveLength(3);
    // Sanity check that the chart actually rendered all six slices.
    expect(container.querySelectorAll('.recharts-pie-sector')).toHaveLength(6);
  });
});

// #10313: two adjacent ~5.5% slices on the same side near 12 o'clock (anchors
// ~12px apart vertically) and a long label near 9 o'clock in a 640px-wide
// chart, the narrowest width that still shows inline labels.
const crowdedAllocation = [
  { name: 'Equity', value: 14.5 },
  { name: 'Bond', value: 5.5 },
  { name: 'Gold', value: 5.5 },
  { name: 'Investment Trust Holdings Plc', value: 40 },
  { name: 'Cash', value: 34.5 },
];

type Box = { left: number; right: number; top: number; bottom: number; text: string };

/** Estimated bounding box of a rendered label, from the same metrics the layout uses. */
const labelBox = (node: Element): Box => {
  const x = Number(node.getAttribute('x'));
  const y = Number(node.getAttribute('y'));
  const text = node.textContent ?? '';
  const width = text.length * INLINE_PIE_LABEL_CHAR_WIDTH;
  const anchor = node.getAttribute('text-anchor');
  const left = anchor === 'end' ? x - width : x;
  const half = INLINE_PIE_LABEL_LINE_HEIGHT / 2;
  return { left, right: left + width, top: y - half, bottom: y + half, text };
};

const intersects = (a: Box, b: Box) =>
  a.left < b.right && b.left < a.right && a.top < b.bottom - 1e-6 && b.top < a.bottom - 1e-6;

describe('collision- and edge-aware pie labels inside a real recharts <Pie> (#10313)', () => {
  it('renders no overlapping labels and keeps every label inside the SVG', () => {
    const width = 640;
    const height = 240;
    const { label, labelLine } = createPieLabelRenderers(
      crowdedAllocation.map((d) => d.value),
      (p) => `${String(p.name)} ${((p.percent ?? 0) * 100).toFixed(2)}%`,
    );
    const { container } = render(
      <PieChart width={width} height={height}>
        <Pie
          dataKey="value"
          data={crowdedAllocation}
          isAnimationActive={false}
          outerRadius="80%"
          labelLine={labelLine}
          label={label}
        />
      </PieChart>,
    );

    const boxes = Array.from(container.querySelectorAll('svg text.recharts-pie-label-text')).map(
      labelBox,
    );
    expect(boxes.length).toBeGreaterThanOrEqual(4);
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        expect(intersects(boxes[i], boxes[j]), `${boxes[i].text} / ${boxes[j].text}`).toBe(false);
      }
    }
    for (const box of boxes) {
      expect(box.left, box.text).toBeGreaterThanOrEqual(0);
      expect(box.right, box.text).toBeLessThanOrEqual(width);
      expect(box.top, box.text).toBeGreaterThanOrEqual(0);
      expect(box.bottom, box.text).toBeLessThanOrEqual(height);
    }
    // The long label near 9 o'clock is truncated rather than clipped.
    expect(boxes.map((b) => b.text)).toContainEqual(expect.stringMatching(/^Investment.*…$/));
    // Each visible label keeps its leader line; hidden labels have none.
    expect(container.querySelectorAll('svg polyline')).toHaveLength(boxes.length);
  });
});
