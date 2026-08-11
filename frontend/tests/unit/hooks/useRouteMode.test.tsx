import { act, renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
vi.mock("@/api", () => ({ getGroups: vi.fn().mockResolvedValue([]) }));
import {
  configContext,
  type ConfigContextValue,
} from "@/ConfigContext";
import { useRouteMode } from "@/hooks/useRouteMode";
import { type ReactNode, useRef } from "react";

/** Minimal config with all tabs enabled including trail. */
const allTabsConfig: ConfigContextValue = {
  ...configContext._currentValue,
  tabs: {
    ...configContext._currentValue.tabs,
    trail: true,
  },
};

describe("useRouteMode", () => {
  it("defaults to group mode on root path", async () => {
    window.history.pushState({}, "", "/");

    const wrapper = ({ children }: { children: ReactNode }) => (
      <MemoryRouter initialEntries={["/"]}>{children}</MemoryRouter>
    );

    const { result } = renderHook(
      () => ({ route: useRouteMode(), location: useLocation() }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.route.mode).toBe("group"));
    expect(result.current.location.pathname).toBe("/");
  });

  it("recognizes trail mode", async () => {
    window.history.pushState({}, "", "/trail");

    // trail is disabled in defaultTabs — supply a config that enables it so the
    // hook does not redirect away from /trail to the first enabled tab.
    const wrapper = ({ children }: { children: ReactNode }) => (
      <configContext.Provider value={allTabsConfig}>
        <MemoryRouter initialEntries={["/trail"]}>{children}</MemoryRouter>
      </configContext.Provider>
    );

    const { result } = renderHook(
      () => ({ route: useRouteMode(), location: useLocation() }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.route.mode).toBe("trail"));
    expect(result.current.location.pathname).toBe("/trail");
  });

  it("uses group slug from query string", async () => {
    window.history.pushState({}, "", "/?group=kids");

    const wrapper = ({ children }: { children: ReactNode }) => (
      <MemoryRouter initialEntries={["/?group=kids"]}>{children}</MemoryRouter>
    );

    const { result } = renderHook(
      () => ({ route: useRouteMode(), location: useLocation() }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.route.mode).toBe("group"));
    expect(result.current.route.selectedGroup).toBe("kids");
  });
  it("uses owner scope from the root query string", async () => {
    window.history.pushState({}, "", "/?owner=steve&account=isa");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <MemoryRouter initialEntries={["/?owner=steve&account=isa"]}>{children}</MemoryRouter>
    );
    const { result } = renderHook(() => useRouteMode(), { wrapper });
    await waitFor(() => expect(result.current.mode).toBe("owner"));
    expect(result.current.selectedOwner).toBe("steve");
    expect(result.current.selectedAccount).toBe("isa");
  });
  it.each(["/", "/?owner=x", "/?owner=x&account=y"])(
    "settles without a render loop for %s",
    async (entry) => {
      window.history.pushState({}, "", entry);
      const wrapper = ({ children }: { children: ReactNode }) => (
        <MemoryRouter initialEntries={[entry]}>{children}</MemoryRouter>
      );
      const { result } = renderHook(
        () => {
          const renderCount = useRef(0);
          renderCount.current += 1;
          return { route: useRouteMode(), renderCount: renderCount.current };
        },
        { wrapper },
      );

      await waitFor(() =>
        expect(result.current.route.mode).toBe(entry.includes("owner=") ? "owner" : "group"),
      );
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
      });
      const settledRenderCount = result.current.renderCount;
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      expect(result.current.renderCount).toBe(settledRenderCount);
    },
  );
  it("navigates to first enabled tab when movers is disabled", async () => {
    window.history.pushState({}, "", "/movers");

    const tabs = {
      group: false,
      owner: true,
      instrument: false,
      performance: false,
      transactions: false,
      trading: false,
      screener: false,
      timeseries: false,
      watchlist: false,
      movers: false,
      market: false,
      allocation: false,
      rebalance: false,
      instrumentadmin: false,
      dataadmin: false,
      virtual: false,
      support: false,
      settings: false,
      pension: false,
      scenario: false,
      reports: false,
    };

    const config: ConfigContextValue = {
      relativeViewEnabled: false,
      disabledTabs: ["movers"],
      tabs,
      theme: "system",
      refreshConfig: async () => {},
      setRelativeViewEnabled: () => {},
      baseCurrency: "GBP",
      setBaseCurrency: () => {},
    };

    const wrapper = ({ children }: { children: ReactNode }) => (
      <configContext.Provider value={config}>
        <MemoryRouter initialEntries={["/movers"]}>{children}</MemoryRouter>
      </configContext.Provider>
    );

    const { result } = renderHook(
      () => ({ route: useRouteMode(), location: useLocation() }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.route.mode).toBe("owner"));
  });
});
