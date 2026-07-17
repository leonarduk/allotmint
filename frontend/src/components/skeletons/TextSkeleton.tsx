interface Props {
  width?: string;
  label: string;
}

/** Skeleton placeholder for a short inline text value. */
export default function TextSkeleton({ width = "3rem", label }: Props) {
  return (
    <span role="status" aria-live="polite" aria-label={label}>
      <span className="sr-only">{label}</span>
      <span
        aria-hidden="true"
        className="inline-block h-3 align-middle bg-gray-700 rounded animate-pulse"
        style={{ width }}
      />
    </span>
  );
}
