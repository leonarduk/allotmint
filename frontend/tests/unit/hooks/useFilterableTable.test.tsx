import { renderHook, act } from "@testing-library/react";
import { useFilterableTable, type Filter } from "@/hooks/useFilterableTable";

type Row = { name: string; age: number; active: boolean };

const rows: Row[] = [
  { name: "Aaron", age: 20, active: false },
  { name: "Bob", age: 25, active: false },
  { name: "Alice", age: 30, active: true },
  { name: "Carol", age: 35, active: true },
];

const filters: Record<string, Filter<Row, unknown>> = {
  search: {
    value: "",
    predicate: (row, value) =>
      typeof value === "string"
        ? row.name.toLowerCase().includes(value.toLowerCase())
        : true,
  },
  onlyActive: {
    value: false,
    predicate: (row, value) =>
      typeof value === "boolean" ? (value ? row.active : true) : true,
  },
} satisfies Record<string, Filter<Row, unknown>>;

describe("useFilterableTable", () => {
  it("filters and sorts rows", () => {
    const { result } = renderHook(() =>
      useFilterableTable(rows, "age", filters)
    );

    expect(result.current.rows.map((r) => r.name)).toEqual([
      "Aaron",
      "Bob",
      "Alice",
      "Carol",
    ]);

    act(() => result.current.handleSort("age"));
    expect(result.current.rows.map((r) => r.name)).toEqual([
      "Carol",
      "Alice",
      "Bob",
      "Aaron",
    ]);

    act(() => result.current.setFilter("search", "a"));
    expect(result.current.rows.map((r) => r.name)).toEqual([
      "Carol",
      "Alice",
      "Aaron",
    ]);

    act(() => result.current.setFilter("onlyActive", true));
    expect(result.current.rows.map((r) => r.name)).toEqual([
      "Carol",
      "Alice",
    ]);

    // eslint-disable-next-line no-constant-condition
    if (false) {
      result.current.setFilter("search", "123");
      result.current.setFilter("onlyActive", true);
    }
  });
});
