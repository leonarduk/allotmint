import { describe, expect, it, vi } from "vitest";
import { mergeBrowserLists, threeWayMerge, unionMerge } from "@/lib/watchlistMerge";
import type { WatchlistsState } from "@/lib/watchlistStore";

const list = (name: string, symbols: string[], id = "default"): WatchlistsState => ({
  activeId: id,
  lists: [{ id, name, symbols }],
});

const state = (activeId: string, ...lists: [string, string, string[]][]): WatchlistsState => ({
  activeId,
  lists: lists.map(([id, name, symbols]) => ({ id, name, symbols })),
});

describe("mergeBrowserLists", () => {
  it("adds only the browser's lists that differ, renaming on a clash", () => {
    const savedState: WatchlistsState = {
      activeId: "a",
      lists: [
        { id: "a", name: "Tech", symbols: ["AAPL"] },
        { id: "b", name: "Same", symbols: ["BP.L"] },
      ],
    };
    const browser: WatchlistsState = {
      activeId: "x",
      lists: [
        { id: "x", name: "tech", symbols: ["MSFT"] },
        { id: "y", name: "Same", symbols: ["BP.L"] },
        { id: "z", name: "New", symbols: [] },
      ],
    };

    const merged = mergeBrowserLists(savedState, browser);

    expect(merged.activeId).toBe("a");
    expect(merged.lists.map((l) => l.name)).toEqual(["Tech", "Same", "tech (this browser)", "New"]);
    expect(new Set(merged.lists.map((l) => l.id)).size).toBe(4);
  });

  it("returns the saved state itself when the browser adds nothing", () => {
    const state = list("Same", ["BP.L"]);
    expect(mergeBrowserLists(state, list("same", ["BP.L"], "other"))).toBe(state);
  });

  it("stops at the list limit", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const many = (prefix: string, n: number): WatchlistsState => ({
      activeId: `${prefix}0`,
      lists: Array.from({ length: n }, (_, i) => ({ id: `${prefix}${i}`, name: `${prefix}${i}`, symbols: [] })),
    });
    expect(mergeBrowserLists(many("s", 49), many("b", 3)).lists).toHaveLength(50);
    vi.restoreAllMocks();
  });
});

describe("threeWayMerge", () => {
  const base = state("a", ["a", "Tech", ["AAPL", "MSFT"]], ["b", "Banks", ["HSBA.L"]]);

  it("applies both sides' symbol adds and removes to the same list", () => {
    const local = state("a", ["a", "Tech", ["AAPL", "MSFT", "NVDA"]], ["b", "Banks", ["HSBA.L"]]);
    const remote = state("a", ["a", "Tech", ["MSFT", "GOOG"]], ["b", "Banks", ["HSBA.L"]]);

    expect(threeWayMerge(base, local, remote).lists[0].symbols).toEqual(["MSFT", "GOOG", "NVDA"]);
  });

  it("removes a symbol removed here even if the other side kept it", () => {
    const local = state("a", ["a", "Tech", ["AAPL"]], ["b", "Banks", ["HSBA.L"]]);
    const remote = state("a", ["a", "Tech", ["AAPL", "MSFT", "GOOG"]], ["b", "Banks", ["HSBA.L"]]);

    expect(threeWayMerge(base, local, remote).lists[0].symbols).toEqual(["AAPL", "GOOG"]);
  });

  it("takes this side's rename, else the other side's", () => {
    const local = state("a", ["a", "Tech here", ["AAPL", "MSFT"]], ["b", "Banks", ["HSBA.L"]]);
    const remote = state("a", ["a", "Tech", ["AAPL", "MSFT"]], ["b", "Banks there", ["HSBA.L"]]);

    expect(threeWayMerge(base, local, remote).lists.map((l) => l.name)).toEqual(["Tech here", "Banks there"]);
  });

  it("keeps deletes from either side unless the other side edited that list", () => {
    const deletedHere = state("a", ["a", "Tech", ["AAPL", "MSFT"]]);
    const untouched = base;
    expect(threeWayMerge(base, deletedHere, untouched).lists.map((l) => l.id)).toEqual(["a"]);

    const editedThere = state("a", ["a", "Tech", ["AAPL", "MSFT"]], ["b", "Banks", ["HSBA.L", "LLOY.L"]]);
    expect(threeWayMerge(base, deletedHere, editedThere).lists.map((l) => l.id)).toEqual(["a", "b"]);

    const deletedThere = state("a", ["a", "Tech", ["AAPL", "MSFT"]]);
    const editedHere = state("a", ["a", "Tech", ["AAPL", "MSFT"]], ["b", "Banks", ["BARC.L"]]);
    expect(threeWayMerge(base, editedHere, deletedThere).lists.map((l) => l.id)).toEqual(["a", "b"]);
  });

  it("adds lists created on either side, renaming a name clash on this side's", () => {
    const local = state("a", ...base.lists.map((l) => [l.id, l.name, l.symbols] as [string, string, string[]]), [
      "x",
      "Energy",
      ["BP.L"],
    ]);
    const remote = state("a", ...base.lists.map((l) => [l.id, l.name, l.symbols] as [string, string, string[]]), [
      "y",
      "energy",
      ["SHEL.L"],
    ]);

    expect(threeWayMerge(base, local, remote).lists.map((l) => l.name)).toEqual([
      "Tech",
      "Banks",
      "energy",
      "Energy (this browser)",
    ]);
  });

  it("follows the list switched to here, else the other side's", () => {
    const switchedHere = { ...base, activeId: "b" };
    expect(threeWayMerge(base, switchedHere, base).activeId).toBe("b");
    const switchedThere = { ...base, activeId: "b" };
    expect(threeWayMerge(base, base, switchedThere).activeId).toBe("b");
  });

  it("never returns an empty state", () => {
    const one = state("a", ["a", "Tech", ["AAPL", "MSFT"]]);
    const deletedHere = state("b", ["b", "Other", []]);
    const remote = state("a", ["a", "Tech", ["AAPL", "MSFT"]]);
    expect(threeWayMerge(one, deletedHere, remote).lists.map((l) => l.id)).toEqual(["b"]);
  });
});

describe("unionMerge", () => {
  it("matches lists by id, keeps the saved names and adds this browser's symbols and lists", () => {
    const local = state("a", ["a", "Tech here", ["AAPL", "NVDA"]], ["x", "Mine", ["BP.L"]]);
    const remote = state("a", ["a", "Tech", ["AAPL", "GOOG"]], ["b", "Banks", []]);

    expect(unionMerge(local, remote)).toEqual(
      state("a", ["a", "Tech", ["AAPL", "GOOG", "NVDA"]], ["b", "Banks", []], ["x", "Mine", ["BP.L"]]),
    );
  });
});
