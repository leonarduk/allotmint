import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useViewportWidth } from "@/hooks/useViewportWidth";

describe("useViewportWidth", () => {
  afterEach(() => vi.restoreAllMocks());

  it("tracks viewport resizes and removes its listener on unmount", () => {
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(1_200);
    const removeEventListener = vi.spyOn(window, "removeEventListener");
    const { result, unmount } = renderHook(() => useViewportWidth());

    expect(result.current).toBe(1_200);
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(900);
    act(() => window.dispatchEvent(new Event("resize")));
    expect(result.current).toBe(900);

    unmount();
    expect(removeEventListener).toHaveBeenCalledWith("resize", expect.any(Function));
  });
});
