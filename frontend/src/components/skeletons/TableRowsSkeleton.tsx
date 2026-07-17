interface Props {
  rows?: number;
  colSpan: number;
  label: string;
  cellClassName?: string;
}

/** Skeleton placeholder rows for use inside an existing table's <tbody>. */
export default function TableRowsSkeleton({
  rows = 3,
  colSpan,
  label,
  cellClassName,
}: Props) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <tr
          key={i}
          role={i === 0 ? "status" : undefined}
          aria-live={i === 0 ? "polite" : undefined}
          aria-label={i === 0 ? label : undefined}
        >
          <td colSpan={colSpan} className={cellClassName}>
            {i === 0 && <span className="sr-only">{label}</span>}
            <div className="h-4 bg-gray-700 rounded animate-pulse" />
          </td>
        </tr>
      ))}
    </>
  );
}
