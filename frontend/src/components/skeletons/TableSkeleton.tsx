import React from "react";

interface Props {
  rows?: number;
  cols?: number;
}

export default function TableSkeleton({ rows = 5, cols = 4 }: Props) {
  return (
    <table className="w-full border border-gray-700 rounded animate-pulse">
      <tbody>
        {Array.from({ length: rows }).map((_, r) => (
          <tr key={r} className="border-b border-gray-700 last:border-b-0">
            {Array.from({ length: cols }).map((_, c) => (
              <td key={c} className="p-2">
                <div className="h-4 bg-gray-700 rounded" />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
