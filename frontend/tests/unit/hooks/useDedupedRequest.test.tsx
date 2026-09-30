import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useDedupedRequest } from "../../../src/hooks/useDedupedRequest";

describe("useDedupedRequest", () => {
  it("executes a single request for a fresh key", async () => {
    const request = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useDedupedRequest(request));

    let value: string | undefined;
    await act(async () => {
      value = await result.current.run("a");
    });

    expect(value).toBe("ok");
    expect(request).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledWith("a");
  });

  it("dedupes concurrent identical requests", async () => {
    let resolveRequest: ((value: string) => void) | undefined;
    const request = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveRequest = resolve;
        }),
    );
    const { result } = renderHook(() => useDedupedRequest(request));

    let first: Promise<string | undefined> | undefined;
    let second: Promise<string | undefined> | undefined;
    act(() => {
      first = result.current.run("a");
      second = result.current.run("a");
    });

    expect(request).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveRequest?.("done");
      await Promise.all([first, second]);
    });

    expect(request).toHaveBeenCalledTimes(1);
  });

  it("keeps the key after a successful request so repeats are skipped", async () => {
    const request = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useDedupedRequest(request));

    await act(async () => {
      await result.current.run("a");
    });
    await act(async () => {
      await result.current.run("a");
    });

    expect(request).toHaveBeenCalledTimes(1);
  });

  it("clears the key on failure so a retry is allowed", async () => {
    const request = vi
      .fn()
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce("ok");
    const { result } = renderHook(() => useDedupedRequest(request));

    await act(async () => {
      await expect(result.current.run("a")).rejects.toThrow("boom");
    });

    let value: string | undefined;
    await act(async () => {
      value = await result.current.run("a");
    });

    expect(value).toBe("ok");
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("clears a specific key via clear(key)", async () => {
    const request = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useDedupedRequest(request));

    await act(async () => {
      await result.current.run("a");
    });
    act(() => {
      result.current.clear(["a"]);
    });
    await act(async () => {
      await result.current.run("a");
    });

    expect(request).toHaveBeenCalledTimes(2);
  });

  it("clears all keys when clear() is called with no arguments", async () => {
    const request = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useDedupedRequest(request));

    await act(async () => {
      await result.current.run("a");
      await result.current.run("b");
    });
    act(() => {
      result.current.clear();
    });
    await act(async () => {
      await result.current.run("a");
      await result.current.run("b");
    });

    expect(request).toHaveBeenCalledTimes(4);
  });

  it("tracks keys independently", async () => {
    const request = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useDedupedRequest(request));

    await act(async () => {
      await result.current.run("a");
      await result.current.run("b");
      await result.current.run("a");
      await result.current.run("b");
    });

    expect(request).toHaveBeenCalledTimes(2);
    expect(request).toHaveBeenNthCalledWith(1, "a");
    expect(request).toHaveBeenNthCalledWith(2, "b");
  });
});
