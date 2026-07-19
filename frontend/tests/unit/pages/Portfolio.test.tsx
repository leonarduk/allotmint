import { useState } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { describe, it, expect, vi, beforeEach } from "vitest";
import PortfolioPage from "@/pages/Portfolio";
import { RouteContext } from "@/contexts/route";
import type { Portfolio } from "@/types";
import * as api from "@/api";

/**
 * Minimal RouteContext stand-in that owns just ``selectedOwner`` as local
 * state, bypassing the app's ``useRouteMode`` (which re-derives the owner
 * from ``location.pathname`` and would otherwise fight this test, since
 * ``useNavigate()`` is globally mocked to a no-op in tests -- see
 * src/setupTests.ts -- so the URL never actually changes).
 */
function OwnerOnlyRouteProvider({ children }: { children: React.ReactNode }) {
  const [selectedOwner, setSelectedOwner] = useState("");
  return (
    <RouteContext.Provider
      value={{
        mode: "owner",
        setMode: () => {},
        selectedOwner,
        setSelectedOwner,
        selectedGroup: "",
        setSelectedGroup: () => {},
      }}
    >
      {children}
    </RouteContext.Provider>
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

vi.mock("@/api");
const mockGetPortfolio = vi.mocked(api.getPortfolio);
const mockGetOwners = vi.mocked(api.getOwners);

describe("Portfolio page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches portfolio whenever owner changes", async () => {
    mockGetOwners.mockResolvedValueOnce([
      { owner: "alice", accounts: [] },
    ]);
    mockGetPortfolio.mockResolvedValueOnce({
      owner: "alice",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    } as Portfolio);
    render(
      <HelmetProvider>
        <MemoryRouter initialEntries={["/portfolio/alice"]}>
          <Routes>
            <Route path="/portfolio/:owner" element={<PortfolioPage />} />
          </Routes>
        </MemoryRouter>
      </HelmetProvider>,
    );

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alice"));
    await screen.findByText(/Approx Total:/);

    mockGetPortfolio.mockClear();
    cleanup();
    mockGetOwners.mockResolvedValueOnce([
      { owner: "bob", accounts: [] },
    ]);
    mockGetPortfolio.mockResolvedValueOnce({
      owner: "bob",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    } as Portfolio);

    render(
      <HelmetProvider>
        <MemoryRouter initialEntries={["/portfolio/bob"]}>
          <Routes>
            <Route path="/portfolio/:owner" element={<PortfolioPage />} />
          </Routes>
        </MemoryRouter>
      </HelmetProvider>,
    );

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("bob"));
    await screen.findByText(/Approx Total:/);
  });

  it("ignores a stale portfolio response that resolves after a newer owner switch", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alice", accounts: [] },
      { owner: "bob", accounts: [] },
    ]);

    const alice = deferred<Portfolio>();
    const bob = deferred<Portfolio>();
    mockGetPortfolio.mockImplementation((owner: string) =>
      owner === "alice" ? alice.promise : bob.promise,
    );

    render(
      <HelmetProvider>
        <MemoryRouter initialEntries={["/portfolio"]}>
          <OwnerOnlyRouteProvider>
            <Routes>
              <Route path="/portfolio" element={<PortfolioPage />} />
            </Routes>
          </OwnerOnlyRouteProvider>
        </MemoryRouter>
      </HelmetProvider>,
    );

    const ownerSelect = await screen.findByLabelText(/Owner/i);
    await userEvent.selectOptions(ownerSelect, "alice");
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alice"));

    await userEvent.selectOptions(ownerSelect, "bob");
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("bob"));

    // Resolve the newer (bob) request first, then the stale (alice) request
    // second -- an out-of-order completion is exactly what happens when the
    // backend is slow, per issue #5180. The stale alice response must not
    // clobber bob's already-rendered data or state.
    bob.resolve({
      owner: "bob",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 200,
      accounts: [
        { account_type: "isa", currency: "GBP", value_estimate_gbp: 200, holdings: [] },
      ],
    } as Portfolio);
    const totalEl = await screen.findByText(/Approx Total:/);
    expect(totalEl.textContent).toMatch(/200/);

    // Resolve inside act() and explicitly await the settled promise (not
    // just a couple of bare microtask ticks) so that if the stale response
    // *were* applied, the resulting setState would have already flushed by
    // the time we assert below -- otherwise this test would pass whether or
    // not the regression guard is in place.
    await act(async () => {
      alice.resolve({
        owner: "alice",
        as_of: "2024-01-01",
        trades_this_month: 0,
        trades_remaining: 0,
        total_value_estimate_gbp: 100,
        accounts: [
          { account_type: "isa", currency: "GBP", value_estimate_gbp: 100, holdings: [] },
        ],
      } as Portfolio);
      await alice.promise;
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.queryByText(/Failed to load portfolio/)).not.toBeInTheDocument();
    expect(screen.getByText(/Approx Total:/).textContent).toMatch(/200/);
  });

  it("shows available owners excluding demo entries", async () => {
    mockGetOwners.mockResolvedValueOnce([
      { owner: "demo", accounts: [] },
      { owner: "steve", accounts: [] },
      { owner: "lucy", accounts: [] },
    ]);

    render(
      <HelmetProvider>
        <MemoryRouter initialEntries={["/portfolio"]}>
          <Routes>
            <Route path="/portfolio" element={<PortfolioPage />} />
          </Routes>
        </MemoryRouter>
      </HelmetProvider>,
    );

    const ownerSelect = await screen.findByLabelText(/Owner/i);
    const values = Array.from(ownerSelect.querySelectorAll("option")).map(
      (option) => option.value,
    );
    expect(values).toContain("steve");
    expect(values).toContain("lucy");
    expect(values).not.toContain("demo");
  });
});
