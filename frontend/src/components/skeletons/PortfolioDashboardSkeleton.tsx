import KPISkeleton from "./KPISkeleton";
import ChartSkeleton from "./ChartSkeleton";

interface Props {
  label?: string;
}

/** Skeleton placeholder mimicking the PortfolioDashboard layout. Pass `label` to announce it to screen readers. */
export default function PortfolioDashboardSkeleton({ label }: Props = {}) {
  const content = (
    <>
      <KPISkeleton />
      <ChartSkeleton />
      <ChartSkeleton />
    </>
  );

  if (!label) return content;

  return (
    <div role="status" aria-live="polite" aria-label={label}>
      <span className="sr-only">{label}</span>
      {content}
    </div>
  );
}
