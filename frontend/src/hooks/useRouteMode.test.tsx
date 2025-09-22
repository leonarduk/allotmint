import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
vi.mock("../api", () => ({ getGroups: vi.fn().mockResolvedValue([]) }));
import {
  configContext,
  type ConfigContextValue,
} from "../ConfigContext";
import { useRouteMode } from "./useRouteMode";
import { type ReactNode } from "react";

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

    const wrapper = ({ children }: { children: ReactNode }) => (
      <MemoryRouter initialEntries={["/trail"]}>{children}</MemoryRouter>
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
        profile: true,
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
    expect(result.current.location.pathname).toBe("/portfolio");
  });
});
