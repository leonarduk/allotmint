import React from "react";
import KPISkeleton from "./KPISkeleton";
import ChartSkeleton from "./ChartSkeleton";

/** Skeleton placeholder mimicking the PortfolioDashboard layout. */
export default function PortfolioDashboardSkeleton() {
  return (
    <>
      <KPISkeleton />
      <ChartSkeleton />
      <ChartSkeleton />
    </>
  );
}
