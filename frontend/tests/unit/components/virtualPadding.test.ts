import { describe, it, expect } from 'vitest';
import { getVirtualSpacerHeights } from '@/components/instrumentTable/virtualPadding';

// Mirrors @tanstack/virtual-core: item offsets are measured from the scroll
// container's origin (so they include scrollMargin), while getTotalSize()
// already has scrollMargin subtracted back out.
const ROW_HEIGHT = 32;
const HEADER_HEIGHT = 130;

const measure = (
  firstIndex: number,
  lastIndex: number,
  scrollMargin: number
) => [
  {
    start: scrollMargin + firstIndex * ROW_HEIGHT,
    end: scrollMargin + (firstIndex + 1) * ROW_HEIGHT,
  },
  {
    start: scrollMargin + lastIndex * ROW_HEIGHT,
    end: scrollMargin + (lastIndex + 1) * ROW_HEIGHT,
  },
];

describe('getVirtualSpacerHeights', () => {
  it('leaves no gap above the first row when scrolled to the top', () => {
    const totalSize = 100 * ROW_HEIGHT;

    const { paddingTop } = getVirtualSpacerHeights(
      measure(0, 9, HEADER_HEIGHT),
      totalSize,
      HEADER_HEIGHT
    );

    expect(paddingTop).toBe(0);
  });

  it('offsets the top spacer by the rows scrolled past, not the header', () => {
    const totalSize = 100 * ROW_HEIGHT;

    const { paddingTop } = getVirtualSpacerHeights(
      measure(20, 29, HEADER_HEIGHT),
      totalSize,
      HEADER_HEIGHT
    );

    expect(paddingTop).toBe(20 * ROW_HEIGHT);
  });

  it('keeps the spacers summing to the un-rendered rows', () => {
    const rowCount = 100;
    const totalSize = rowCount * ROW_HEIGHT;
    const firstIndex = 20;
    const lastIndex = 29;

    const { paddingTop, paddingBottom } = getVirtualSpacerHeights(
      measure(firstIndex, lastIndex, HEADER_HEIGHT),
      totalSize,
      HEADER_HEIGHT
    );
    const renderedRows = lastIndex - firstIndex + 1;

    expect(paddingTop + paddingBottom).toBe(
      (rowCount - renderedRows) * ROW_HEIGHT
    );
    expect(paddingBottom).toBe((rowCount - lastIndex - 1) * ROW_HEIGHT);
  });

  it('behaves the same when no scroll margin is set', () => {
    const totalSize = 100 * ROW_HEIGHT;

    expect(getVirtualSpacerHeights(measure(20, 29, 0), totalSize, 0)).toEqual({
      paddingTop: 20 * ROW_HEIGHT,
      paddingBottom: 70 * ROW_HEIGHT,
    });
  });

  it('returns no padding when nothing is virtualized', () => {
    expect(getVirtualSpacerHeights([], 0, HEADER_HEIGHT)).toEqual({
      paddingTop: 0,
      paddingBottom: 0,
    });
  });

  it('never returns a negative height when the measurements are stale', () => {
    // getTotalSize() can lag the rendered items by a frame while rows are
    // filtered out from under the virtualizer.
    const { paddingTop, paddingBottom } = getVirtualSpacerHeights(
      measure(0, 9, HEADER_HEIGHT),
      0,
      HEADER_HEIGHT
    );

    expect(paddingTop).toBe(0);
    expect(paddingBottom).toBe(0);
  });
});
