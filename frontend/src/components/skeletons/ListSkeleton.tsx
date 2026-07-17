interface Props {
  rows?: number;
  label: string;
  /** Set false when an ancestor already provides the role="status" region. */
  wrap?: boolean;
}

function ListSkeletonRows({ rows }: { rows: number }) {
  return (
    <ul style={{ listStyle: "none", padding: 0 }} aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i} style={{ marginBottom: "0.5rem" }}>
          <div className="h-4 mb-1 bg-gray-700 rounded animate-pulse w-3/4" />
          <div className="h-3 bg-gray-700 rounded animate-pulse w-1/3" />
        </li>
      ))}
    </ul>
  );
}

/** Skeleton placeholder for short lists (drawers, sidebars, alert feeds). */
export default function ListSkeleton({ rows = 3, label, wrap = true }: Props) {
  if (!wrap) return <ListSkeletonRows rows={rows} />;
  return (
    <div role="status" aria-live="polite" aria-label={label}>
      <span className="sr-only">{label}</span>
      <ListSkeletonRows rows={rows} />
    </div>
  );
}
