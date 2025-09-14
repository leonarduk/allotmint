import { describe, expect, it } from 'vitest';
import { dedupeSections, type Section } from './dedupeSections';

describe('dedupeSections', () => {
  it('merges sections with identical titles', () => {
    const input: Section<number>[] = [
      { title: 'A', cards: [1] },
      { title: 'B', cards: [2] },
      { title: 'A', cards: [3, 4] },
    ];

    const result = dedupeSections(input);

    expect(result).toEqual([
      { title: 'A', cards: [1, 3, 4] },
      { title: 'B', cards: [2] },
    ]);

    // ensure original array was not mutated
    expect(input[0].cards).toEqual([1]);
  });
});
