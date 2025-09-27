/** Skeleton placeholder for KPI metric grids. */
export default function KPISkeleton() {
  return (
    <div className="grid grid-cols-2 gap-4 p-4 mb-4 bg-gray-900 border border-gray-700 rounded sm:grid-cols-3 md:grid-cols-5">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex flex-col animate-pulse">
          <div className="h-4 mb-2 bg-gray-700 rounded w-3/4" />
          <div className="h-6 bg-gray-700 rounded w-1/2" />
        </div>
      ))}
    </div>
  );
}
