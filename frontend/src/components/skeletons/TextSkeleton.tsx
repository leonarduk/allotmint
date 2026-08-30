interface Props {
  width?: string;
  label: string;
}

/**
 * Skeleton placeholder for a short inline text value.
 *
 * Pass a non-empty `label` when this is the only (or first) skeleton
 * announcing a loading state, so screen readers hear it once. Pass an empty
 * `label` (`""`) for every other decorative instance in the same loading
 * region -- e.g. one `TextSkeleton` per KPI tile -- so repeating the same
 * instance doesn't produce a live region per instance; wrap the whole
 * section in a single `LoadingStatus` for the one real announcement instead.
 */
export default function TextSkeleton({ width = "3rem", label }: Props) {
  const pulse = (
    <span
      aria-hidden="true"
      className="inline-block h-3 align-middle bg-gray-700 rounded animate-pulse"
      style={{ width }}
    />
  );

  if (!label) return pulse;

  return (
    <span role="status" aria-live="polite" aria-label={label}>
      <span className="sr-only">{label}</span>
      {pulse}
    </span>
  );
}
