import { render, screen, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useCallback, useState } from "react";
import { useFetch } from "@/hooks/useFetch";
import { clearFetchCache } from "@/utils/fetchCache";

/**
 * Covers the stale-while-revalidate cache added so that leaving a page and
 * coming back does not re-pay a cold load. The behaviour under test is
 * specifically what happens across *unmount*, which is why every case here
 * mounts, unmounts and mounts again rather than just re-rendering.
 */

type ProbeProps = {
  fetcher: () => Promise<string>;
  cacheKey?: string | null;
  ttlMs?: number;
};

function Probe({ fetcher, cacheKey = null, ttlMs }: ProbeProps) {
  const fn = useCallback(fetcher, [fetcher]);
  const { data, loading, error, refetch } = useFetch<string>(
    fn,
    [],
    true,
    { cacheKey, ...(ttlMs === undefined ? {} : { ttlMs }) },
  );
  return (
    <div>
      <span data-testid="data">{data ?? "none"}</span>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="error">{error ? error.message : "none"}</span>
      <button type="button" onClick={refetch}>
        refetch
      </button>
    </div>
  );
}

describe("useFetch result cache", () => {
  beforeEach(() => {
    clearFetchCache();
  });

  afterEach(() => {
    vi.useRealTimers();
    clearFetchCache();
  });

  it("without a cacheKey, refetches on every mount (unchanged behaviour)", async () => {
    const fetcher = vi.fn().mockResolvedValue("value");

    const first = render(<Probe fetcher={fetcher} />);
    await screen.findByText("value");
    first.unmount();

    render(<Probe fetcher={fetcher} />);
    await screen.findByText("value");

    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("with a cacheKey, a remount inside the TTL makes no request at all", async () => {
    const fetcher = vi.fn().mockResolvedValue("value");

    const first = render(<Probe fetcher={fetcher} cacheKey="k" />);
    await screen.findByText("value");
    first.unmount();

    render(<Probe fetcher={fetcher} cacheKey="k" />);

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("data")).toHaveTextContent("value");
  });

  it("renders cached data on the first commit, never a loading state", async () => {
    const fetcher = vi.fn().mockResolvedValue("value");

    const first = render(<Probe fetcher={fetcher} cacheKey="k" />);
    await screen.findByText("value");
    first.unmount();

    render(<Probe fetcher={fetcher} cacheKey="k" />);

    // Asserted synchronously: this is the flash of skeleton the cache exists
    // to remove, so it must be absent on the very first commit, not merely
    // gone by the time the microtask queue drains.
    expect(screen.getByTestId("loading")).toHaveTextContent("false");
    expect(screen.getByTestId("data")).toHaveTextContent("value");
  });

  it("past the TTL, shows the stale value immediately and revalidates behind it", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce("old")
      .mockResolvedValueOnce("new");

    const first = render(<Probe fetcher={fetcher} cacheKey="k" ttlMs={50} />);
    await screen.findByText("old");
    first.unmount();

    await new Promise((resolve) => setTimeout(resolve, 60));

    render(<Probe fetcher={fetcher} cacheKey="k" ttlMs={50} />);

    // Stale value on screen straight away, with no skeleton...
    expect(screen.getByTestId("data")).toHaveTextContent("old");
    expect(screen.getByTestId("loading")).toHaveTextContent("false");

    // ...replaced once the background request lands.
    await screen.findByText("new");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("keeps stale data and reports no error when a background revalidation fails", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce("old")
      .mockRejectedValueOnce(new Error("network down"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    const first = render(<Probe fetcher={fetcher} cacheKey="k" ttlMs={50} />);
    await screen.findByText("old");
    first.unmount();

    await new Promise((resolve) => setTimeout(resolve, 60));
    render(<Probe fetcher={fetcher} cacheKey="k" ttlMs={50} />);

    await waitFor(() => expect(warn).toHaveBeenCalled());

    // Callers treat `error` as "replace the page with a retry prompt", so a
    // failed silent refresh must not surface one while usable data is shown.
    expect(screen.getByTestId("data")).toHaveTextContent("old");
    expect(screen.getByTestId("error")).toHaveTextContent("none");
    warn.mockRestore();
  });

  it("surfaces the error when the very first load fails and nothing is cached", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("boom"));

    render(<Probe fetcher={fetcher} cacheKey="k" />);

    await screen.findByText("boom");
    expect(screen.getByTestId("data")).toHaveTextContent("none");
  });

  it("refetch ignores a fresh cache entry and refreshes it", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce("old")
      .mockResolvedValueOnce("new");

    render(<Probe fetcher={fetcher} cacheKey="k" />);
    await screen.findByText("old");

    act(() => {
      screen.getByRole("button", { name: "refetch" }).click();
    });

    await screen.findByText("new");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("shares one request between two components mounted on the same key", async () => {
    let resolveFetch: ((value: string) => void) | undefined;
    const fetcher = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveFetch = resolve;
        }),
    );

    render(
      <>
        <Probe fetcher={fetcher} cacheKey="k" />
        <Probe fetcher={fetcher} cacheKey="k" />
      </>,
    );

    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFetch?.("value");
    });

    expect(screen.getAllByTestId("data").map((n) => n.textContent)).toEqual([
      "value",
      "value",
    ]);
  });

  it("drops an in-flight result if the cache is cleared before it lands", async () => {
    // The price-refresh sequence: a request is already in flight, the user hits
    // refresh (which clears the cache), and the older request then settles. Its
    // data predates the refresh, so it must not be written back and served for
    // a further TTL.
    let resolveFetch: ((value: string) => void) | undefined;
    const slowFetcher = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveFetch = resolve;
        }),
    );

    const first = render(<Probe fetcher={slowFetcher} cacheKey="k" />);

    clearFetchCache();

    await act(async () => {
      resolveFetch?.("pre-refresh");
    });
    first.unmount();

    // A fresh mount must go to the network rather than find "pre-refresh"
    // sitting in the cache.
    const freshFetcher = vi.fn().mockResolvedValue("post-refresh");
    render(<Probe fetcher={freshFetcher} cacheKey="k" />);

    await screen.findByText("post-refresh");
    expect(freshFetcher).toHaveBeenCalledTimes(1);
  });

  it("swaps to the new key's data on the same commit when the key changes", async () => {
    const fetcher = vi.fn(async () => "b-value");

    // Seed "a" so a stale render of it would be visible if the key change were
    // deferred to an effect rather than applied during render.
    const seed = render(
      <Probe fetcher={vi.fn(async () => "a-value")} cacheKey="a" />,
    );
    await screen.findByText("a-value");
    seed.unmount();

    function Switcher() {
      const [key, setKey] = useState("a");
      return (
        <>
          <button type="button" onClick={() => setKey("b")}>
            switch
          </button>
          <Probe fetcher={fetcher} cacheKey={key} />
        </>
      );
    }

    render(<Switcher />);
    expect(screen.getByTestId("data")).toHaveTextContent("a-value");

    act(() => {
      screen.getByRole("button", { name: "switch" }).click();
    });

    // "a-value" must be gone the moment the key changes, not one commit later.
    expect(screen.getByTestId("data")).not.toHaveTextContent("a-value");
    await screen.findByText("b-value");
  });
});
