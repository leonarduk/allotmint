import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { Pie, PieChart } from 'recharts';
import { renderPieLabelLine, withSmallSliceLabelsHidden } from '../../../src/lib/pieLabels';

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
