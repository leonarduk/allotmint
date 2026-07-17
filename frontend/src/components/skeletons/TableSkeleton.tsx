interface Props {
  rows?: number;
  columns?: number;
  label: string;
}

/** Skeleton placeholder for a full table (thead is omitted, rows only). */
export default function TableSkeleton({ rows = 4, columns = 3, label }: Props) {
  return (
    <div role="status" aria-live="polite" aria-label={label}>
      <span className="sr-only">{label}</span>
      <table className="w-full border-collapse" aria-hidden="true">
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: columns }).map((_, c) => (
                <td key={c} className="border border-gray-700 p-2">
                  <div className="h-4 bg-gray-700 rounded animate-pulse" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
