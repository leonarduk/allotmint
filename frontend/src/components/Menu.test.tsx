import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import i18n from "../i18n";
import Menu from "./Menu";
import { configContext, type ConfigContextValue } from "../ConfigContext";

describe("Menu", () => {
  it("renders support toggle link", () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Support" })).toHaveAttribute(
      "href",
      "/support",
    );
    expect(screen.queryByRole("link", { name: "Logs" })).toBeNull();
  });

  it("shows support tabs on support route", () => {
    render(
      <MemoryRouter initialEntries={["/support"]}>
        <Menu />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Logs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Support" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("hides support toggle when support tab disabled", () => {
    const config: ConfigContextValue = {
      relativeViewEnabled: false,
      disabledTabs: ["support"],
      tabs: {
        group: true,
        owner: true,
        instrument: true,
        performance: true,
        transactions: true,
        screener: true,
        trading: true,
        timeseries: true,
        watchlist: true,
        movers: true,
        instrumentadmin: true,
        dataadmin: true,
        virtual: true,
        support: false,
        settings: true,
        profile: false,
        reports: true,
        scenario: true,
        logs: true,
      },
      theme: "system",
      baseCurrency: "GBP",
      refreshConfig: async () => {},
      setRelativeViewEnabled: () => {},
      setBaseCurrency: () => {},
    };
    render(
      <configContext.Provider value={config}>
        <MemoryRouter>
          <Menu />
        </MemoryRouter>
      </configContext.Provider>,
    );
    expect(screen.queryByRole("link", { name: "Support" })).toBeNull();
  });

  it("renders logout button when callback provided", () => {
    const onLogout = vi.fn();
    i18n.changeLanguage("fr");
    render(
      <MemoryRouter>
        <Menu onLogout={onLogout} />
      </MemoryRouter>,
    );
    const btn = screen.getByRole("button", { name: "Déconnexion" });
    fireEvent.click(btn);
    expect(onLogout).toHaveBeenCalled();
    i18n.changeLanguage("en");
  });
});
