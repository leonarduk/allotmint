type VirtualRowBounds = {
  start: number;
  end: number;
};

export type VirtualSpacerHeights = {
  paddingTop: number;
  paddingBottom: number;
};

/**
 * Convert virtual item offsets into the spacer-row heights that pad a
 * virtualized `<tbody>`.
 *
 * Virtual item offsets are measured from the scroll container's origin, so they
 * include `scrollMargin` — the height of the `<thead>` the rows begin below. The
 * spacer rows themselves live inside `<tbody>`, which already sits below
 * `<thead>` in normal flow, so that offset has to come back off; leaving it in
 * renders a blank band the height of the header above the first row (#7781).
 *
 * `totalSize` (`Virtualizer.getTotalSize()`) already excludes `scrollMargin`, so
 * only the item offsets are adjusted here.
 */
export function getVirtualSpacerHeights(
  virtualRows: VirtualRowBounds[],
  totalSize: number,
  scrollMargin: number
): VirtualSpacerHeights {
  if (!virtualRows.length) {
    return { paddingTop: 0, paddingBottom: 0 };
  }

  const first = virtualRows[0];
  const last = virtualRows[virtualRows.length - 1];

  return {
    paddingTop: Math.max(first.start - scrollMargin, 0),
    paddingBottom: Math.max(totalSize - (last.end - scrollMargin), 0),
  };
}
