import { useMemo, useState } from "react";

export type Filter<T, V> = {
  value: V;
  predicate: (row: T, value: V) => boolean;
};

export type TableComparator<T> = (
  a: T,
  b: T,
  sortKey: keyof T,
  asc: boolean,
) => number | null | undefined;

export function useFilterableTable<
  T,
  F extends Record<string, Filter<T, unknown>>
>(
  rows: T[],
  initialSortKey: keyof T,
  initialFilters: F,
  comparator?: TableComparator<T>,
) {
  const [sortKey, setSortKey] = useState<keyof T>(initialSortKey);
  const [asc, setAsc] = useState(true);
  const [filters, setFilters] = useState<F>(initialFilters);

  function handleSort(key: keyof T) {
    if (sortKey === key) {
      setAsc(!asc);
    } else {
      setSortKey(key);
      setAsc(true);
    }
  }

  function setFilter<FKey extends keyof F>(name: FKey, value: F[FKey]["value"]) {
    setFilters((prev) => ({
      ...prev,
      [name]: { ...prev[name], value },
    }));
  }

  const filtered = useMemo(() => {
    return rows.filter((row) =>
      Object.values(filters).every(({ value, predicate }) =>
        predicate(row, value)
      )
    );
  }, [rows, filters]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      if (comparator) {
        const result = comparator(a, b, sortKey, asc);
        if (result !== undefined && result !== null && result !== 0) {
          return result;
        }
      }
      const va = a[sortKey];
      const vb = b[sortKey];
      if (typeof va === "string" || typeof vb === "string") {
        const sa = va == null ? "" : String(va);
        const sb = vb == null ? "" : String(vb);
        return asc ? sa.localeCompare(sb) : sb.localeCompare(sa);
      }
      const na = (va as number) ?? 0;
      const nb = (vb as number) ?? 0;
      return asc ? na - nb : nb - na;
    });
  }, [filtered, sortKey, asc, comparator]);

  const filterValues = useMemo(() => {
    return Object.fromEntries(
      Object.entries(filters).map(([k, { value }]) => [k, value])
    ) as { [K in keyof F]: F[K]["value"] };
  }, [filters]);

  return { rows: sorted, sortKey, asc, handleSort, filters: filterValues, setFilter };
}
