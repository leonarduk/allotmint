import type { ReactNode } from "react";

interface Props {
  label: string;
  children: ReactNode;
  className?: string;
}

/** Wraps a visual skeleton so screen readers still announce a loading state. */
export default function LoadingStatus({ label, children, className }: Props) {
  return (
    <div role="status" aria-live="polite" aria-label={label} className={className}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}
