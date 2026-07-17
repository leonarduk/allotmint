interface Props {
  height?: number;
  label?: string;
}

/** Skeleton placeholder for charts. Pass `label` to announce it to screen readers. */
export default function ChartSkeleton({ height = 240, label }: Props = {}) {
  return (
    <div
      role={label ? "status" : undefined}
      aria-live={label ? "polite" : undefined}
      aria-label={label}
      className="w-full mb-4 bg-gray-900 border border-gray-700 rounded animate-pulse"
      style={{ height }}
    />
  );
}
