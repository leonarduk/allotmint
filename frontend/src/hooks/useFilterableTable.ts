import {useMemo, useState} from "react";

export type Filter<T, V> = {
  value: V;
  predicate: (row: T, value: V) => boolean;
};

export function useFilterableTable<
  T,
  F extends Record<string, Filter<T, unknown>>,
>(rows: T[], initialSortKey: keyof T, initialFilters: F) {
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

  function setFilter<FKey extends keyof F>(
    name: FKey,
    value: F[FKey]["value"]
  ) {
    setFilters((prev) => ({
      ...prev,
      [name]: {...prev[name], value},
    }));
  }

  const filtered = useMemo(() => {
    return rows.filter((row) =>
      Object.values(filters).every(({value, predicate}) =>
        predicate(row, value)
      )
    );
  }, [rows, filters]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (typeof va === "string" && typeof vb === "string") {
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      const na = (va as number) ?? 0;
      const nb = (vb as number) ?? 0;
      return asc ? na - nb : nb - na;
    });
  }, [filtered, sortKey, asc]);

  const filterValues = useMemo(() => {
    return Object.fromEntries(
      Object.entries(filters).map(([k, {value}]) => [k, value])
    ) as {[K in keyof F]: F[K]["value"]};
  }, [filters]);

  return {
    rows: sorted,
    sortKey,
    asc,
    handleSort,
    filters: filterValues,
    setFilter,
  };
}
