import { act, renderHook } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useAsyncItemState } from "@/hooks/useAsyncItemState";

describe("useAsyncItemState (issue #7244)", () => {
  it("starts with nothing pending or errored", () => {
    const { result } = renderHook(() => useAsyncItemState());

    expect(result.current.pendingIds.size).toBe(0);
    expect(result.current.errorIds.size).toBe(0);
  });

  it("start marks an id pending and succeed clears it", () => {
    const { result } = renderHook(() => useAsyncItemState());

    act(() => result.current.start("a"));
    expect(result.current.pendingIds.has("a")).toBe(true);

    act(() => result.current.succeed("a"));
    expect(result.current.pendingIds.has("a")).toBe(false);
    expect(result.current.errorIds.has("a")).toBe(false);
  });

  it("fail clears pending and records the error", () => {
    const { result } = renderHook(() => useAsyncItemState());

    act(() => result.current.start("a"));
    act(() => result.current.fail("a"));

    expect(result.current.pendingIds.has("a")).toBe(false);
    expect(result.current.errorIds.has("a")).toBe(true);
  });

  it("start clears a prior error for the same id (retry)", () => {
    const { result } = renderHook(() => useAsyncItemState());

    act(() => result.current.fail("a"));
    act(() => result.current.start("a"));

    expect(result.current.errorIds.has("a")).toBe(false);
    expect(result.current.pendingIds.has("a")).toBe(true);
  });

  it("tracks several ids independently while in flight", () => {
    const { result } = renderHook(() => useAsyncItemState());

    act(() => result.current.start("a"));
    act(() => result.current.start("b"));
    expect(result.current.pendingIds.has("a")).toBe(true);
    expect(result.current.pendingIds.has("b")).toBe(true);

    // A settling first: B must stay pending and A's failure must not touch B.
    act(() => result.current.fail("a"));
    expect(result.current.pendingIds.has("a")).toBe(false);
    expect(result.current.pendingIds.has("b")).toBe(true);
    expect(result.current.errorIds.has("a")).toBe(true);
    expect(result.current.errorIds.has("b")).toBe(false);

    act(() => result.current.succeed("b"));
    expect(result.current.pendingIds.size).toBe(0);
    expect(result.current.errorIds.has("a")).toBe(true);
  });

  it("reset clears pending and error for the given id only", () => {
    const { result } = renderHook(() => useAsyncItemState());

    act(() => result.current.fail("a"));
    act(() => result.current.start("b"));
    act(() => result.current.reset("a"));

    expect(result.current.errorIds.has("a")).toBe(false);
    expect(result.current.pendingIds.has("b")).toBe(true);

    act(() => result.current.reset("b"));
    expect(result.current.pendingIds.size).toBe(0);
  });

  it("returns stable transition callbacks across renders", () => {
    const { result } = renderHook(() => useAsyncItemState());
    const first = result.current;

    act(() => result.current.start("a"));

    expect(result.current.start).toBe(first.start);
    expect(result.current.succeed).toBe(first.succeed);
    expect(result.current.fail).toBe(first.fail);
    expect(result.current.reset).toBe(first.reset);
  });
});
