import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import {
  configContext,
  type ConfigContextValue,
} from "../ConfigContext";
import { useRouteMode } from "./useRouteMode";
import { type ReactNode } from "react";

describe("useRouteMode", () => {
  it("navigates to first enabled tab when movers is disabled", async () => {
    window.history.pushState({}, "", "/movers");

    const tabs = {
      group: false,
      owner: true,
      instrument: false,
      performance: false,
      transactions: false,
      screener: false,
      timeseries: false,
      watchlist: false,
      movers: false,
      dataadmin: false,
      virtual: false,
      support: false,
      scenario: false,
      reports: false,
    };

    const config: ConfigContextValue = {
      relativeViewEnabled: false,
      disabledTabs: ["movers"],
      tabs,
      theme: "system",
      refreshConfig: async () => {},
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
    expect(result.current.location.pathname).toBe("/member");
  });
});
