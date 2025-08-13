import { useMemo, useState } from "react";

export function useSortableTable<T>(rows: T[], initialSortKey: keyof T) {
  const [sortKey, setSortKey] = useState<keyof T>(initialSortKey);
  const [asc, setAsc] = useState(true);

  function handleSort(key: keyof T) {
    if (sortKey === key) {
      setAsc(!asc);
    } else {
      setSortKey(key);
      setAsc(true);
    }
  }

  const sorted = useMemo(() => {
    return [...rows].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (typeof va === "string" && typeof vb === "string") {
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      const na = (va as number) ?? 0;
      const nb = (vb as number) ?? 0;
      return asc ? na - nb : nb - na;
    });
  }, [rows, sortKey, asc]);

  return { sorted, sortKey, asc, handleSort };
}
