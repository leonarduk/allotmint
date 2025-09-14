import React from "react";

export default function KPISkeleton() {
  return (
    <div className="flex gap-8 mb-4 p-4 bg-gray-900 border border-gray-700 rounded animate-pulse">
      {Array.from({ length: 3 }).map((_, idx) => (
        <div key={idx} className="flex flex-col w-24 gap-2">
          <div className="h-3 bg-gray-700 rounded" />
          <div className="h-5 bg-gray-700 rounded" />
        </div>
      ))}
    </div>
  );
}
