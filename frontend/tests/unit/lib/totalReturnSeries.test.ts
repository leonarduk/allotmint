import { describe, expect, it } from 'vitest';
import { withTotalReturn } from '@/lib/totalReturnSeries';

describe('withTotalReturn (#10128)', () => {
  it('rebases the ledger total return to the first comparison date', () => {
    const points = [
      { date: '2024-03-01', portfolio: 0, benchmark: 0 },
      { date: '2024-03-04', portfolio: 0.01, benchmark: 0.02 },
      { date: '2024-03-05', portfolio: 0.02, benchmark: 0.03 },
    ];
    const history = [
      { date: '2024-02-28', value: 1000, cumulative_return: 0 },
      { date: '2024-03-01', value: 1000, cumulative_return: 0.1 },
      { date: '2024-03-04', value: 1000, cumulative_return: 0.21 },
    ];

    const out = withTotalReturn(points, history);

    expect(out[0].total_return).toBeCloseTo(0);
    expect(out[1].total_return).toBeCloseTo(1.21 / 1.1 - 1);
    // No history for that date: null, never a made-up 0.
    expect(out[2].total_return).toBeNull();
    expect(out[1].benchmark).toBe(0.02);
  });

  it('gives every point null when the history has no total return', () => {
    const out = withTotalReturn(
      [{ date: '2024-03-01', portfolio: 0, benchmark: 0 }],
      [{ date: '2024-03-01', value: 1000, cumulative_return: null }]
    );

    expect(out[0].total_return).toBeNull();
  });
});
