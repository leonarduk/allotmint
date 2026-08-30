interface Props {
  rows?: number;
  colSpan: number;
  label: string;
  cellClassName?: string;
}

/**
 * Skeleton placeholder rows for use inside an existing table's <tbody>.
 *
 * Pass a non-empty `label` to announce it once (on the first row). Pass an
 * empty `label` (`""`) when a section already has its own single
 * announcement elsewhere (e.g. a wrapping `LoadingStatus`) so this instance
 * stays purely decorative instead of adding a second live region.
 */
export default function TableRowsSkeleton({
  rows = 3,
  colSpan,
  label,
  cellClassName,
}: Props) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i}>
          <td colSpan={colSpan} className={cellClassName}>
            {i === 0 && label && (
              <span role="status" aria-live="polite" aria-label={label} className="sr-only">
                {label}
              </span>
            )}
            <div className="h-4 bg-gray-700 rounded animate-pulse" />
          </td>
        </tr>
      ))}
    </>
  );
}
