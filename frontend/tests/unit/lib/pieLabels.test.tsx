import { describe, expect, it } from 'vitest';
import { isValidElement } from 'react';
import { render } from '@testing-library/react';
import type { PieLabelRenderProps } from 'recharts';
import {
  MIN_INLINE_PIE_LABEL_FRACTION,
  isPieSliceLabelable,
  renderPieLabelLine,
  withSmallSliceLabelsHidden,
} from '../../../src/lib/pieLabels';

const points = [
  { x: 0, y: 0 },
  { x: 10, y: 10 },
];

describe('pieLabels (#7630)', () => {
  it('treats the threshold as inclusive and missing percent as unlabelable', () => {
    expect(isPieSliceLabelable(MIN_INLINE_PIE_LABEL_FRACTION)).toBe(true);
    expect(isPieSliceLabelable(0.3698)).toBe(true);
    expect(isPieSliceLabelable(0.009)).toBe(false);
    expect(isPieSliceLabelable(undefined)).toBe(false);
  });

  it('formats large slices and returns an empty element for small slices', () => {
    const label = withSmallSliceLabelsHidden((p) => `${String(p.name)} ${p.percent}`);
    expect(label({ name: 'Cash', percent: 0.37 } as PieLabelRenderProps)).toBe('Cash 0.37');

    // The demo allocation's adjacent sub-2% slices that collided in the issue.
    for (const percent of [0.0185, 0.009, 0.0165]) {
      const out = label({ name: 'Fund', percent } as PieLabelRenderProps);
      expect(isValidElement(out)).toBe(true);
      const { container } = render(<svg>{out}</svg>);
      expect(container.querySelector('svg')?.textContent).toBe('');
    }
  });

  it('draws leader lines only for labelable slices', () => {
    const { container: big } = render(
      <svg>{renderPieLabelLine({ percent: 0.3, points, stroke: '#123' })}</svg>,
    );
    const line = big.querySelector('polyline');
    expect(line?.getAttribute('points')).toBe('0,0 10,10');
    expect(line?.getAttribute('stroke')).toBe('#123');

    const { container: small } = render(
      <svg>{renderPieLabelLine({ percent: 0.01, points })}</svg>,
    );
    expect(small.querySelector('polyline')).toBeNull();
  });
});
