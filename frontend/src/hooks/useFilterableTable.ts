import { useMemo } from "react";

export type FilterPredicates<T> = Partial<
    Record<keyof T, (value: T[keyof T], row: T) => boolean>
>;

export function useFilterableTable<T>(
    rows: T[],
    filters: FilterPredicates<T>
): T[] {
    return useMemo(() => {
        return rows.filter((row) =>
            Object.entries(filters).every(([key, predicate]) => {
                if (!predicate) return true;
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const value = (row as any)[key];
                return predicate(value, row);
            })
        );
    }, [rows, filters]);
}
