import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useDedupedRequest } from "../../../src/hooks/useDedupedRequest";

describe("useDedupedRequest", () => {
  it("executes a single request for a fresh key", async () => {
    const thunk = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useDedupedRequest<string>());

    let value: string | undefined;
    await act(async () => {
      value = await result.current.run("a", thunk);
    });

    expect(value).toBe("ok");
    expect(thunk).toHaveBeenCalledTimes(1);
  });

  it("never passes the dedupe key to the request (#8576)", async () => {
    // Regression: the hook used to call request(key), so a composite dedupe
    // key such as "alex::" leaked into the request as the owner and produced
    // GET /portfolio/alex:: (404).
    const fetchOwner = vi.fn((owner: string) => Promise.resolve(owner));
    const { result } = renderHook(() => useDedupedRequest<string>());

    let value: string | undefined;
    await act(async () => {
      value = await result.current.run("alex::2024-01-01", () =>
        fetchOwner("alex"),
      );
    });

    expect(value).toBe("alex");
    expect(fetchOwner).toHaveBeenCalledTimes(1);
    expect(fetchOwner).toHaveBeenCalledWith("alex");
  });

  it("dedupes concurrent identical requests", async () => {
    let resolveRequest: ((value: string) => void) | undefined;
    const thunk = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveRequest = resolve;
        }),
    );
    const { result } = renderHook(() => useDedupedRequest<string>());

    let first: Promise<string | undefined> | undefined;
    let second: Promise<string | undefined> | undefined;
    act(() => {
      first = result.current.run("a", thunk);
      second = result.current.run("a", thunk);
    });

    expect(thunk).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveRequest?.("done");
      await Promise.all([first, second]);
    });

    expect(thunk).toHaveBeenCalledTimes(1);
  });

  it("keeps the key after a successful request so repeats are skipped", async () => {
    const thunk = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useDedupedRequest<string>());

    await act(async () => {
      await result.current.run("a", thunk);
    });
    await act(async () => {
      await result.current.run("a", thunk);
    });

    expect(thunk).toHaveBeenCalledTimes(1);
  });

  it("clears the key on failure so a retry is allowed", async () => {
    const thunk = vi
      .fn()
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce("ok");
    const { result } = renderHook(() => useDedupedRequest<string>());

    await act(async () => {
      await expect(result.current.run("a", thunk)).rejects.toThrow("boom");
    });

    let value: string | undefined;
    await act(async () => {
      value = await result.current.run("a", thunk);
    });

    expect(value).toBe("ok");
    expect(thunk).toHaveBeenCalledTimes(2);
  });

  it("clears a specific key via clear(key)", async () => {
    const thunk = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useDedupedRequest<string>());

    await act(async () => {
      await result.current.run("a", thunk);
    });
    act(() => {
      result.current.clear(["a"]);
    });
    await act(async () => {
      await result.current.run("a", thunk);
    });

    expect(thunk).toHaveBeenCalledTimes(2);
  });

  it("clears all keys when clear() is called with no arguments", async () => {
    const thunk = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useDedupedRequest<string>());

    await act(async () => {
      await result.current.run("a", thunk);
      await result.current.run("b", thunk);
    });
    act(() => {
      result.current.clear();
    });
    await act(async () => {
      await result.current.run("a", thunk);
      await result.current.run("b", thunk);
    });

    expect(thunk).toHaveBeenCalledTimes(4);
  });

  it("tracks keys independently", async () => {
    const thunkA = vi.fn().mockResolvedValue("a");
    const thunkB = vi.fn().mockResolvedValue("b");
    const { result } = renderHook(() => useDedupedRequest<string>());

    await act(async () => {
      await result.current.run("a", thunkA);
      await result.current.run("b", thunkB);
      await result.current.run("a", thunkA);
      await result.current.run("b", thunkB);
    });

    expect(thunkA).toHaveBeenCalledTimes(1);
    expect(thunkB).toHaveBeenCalledTimes(1);
  });
});
