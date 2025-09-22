import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import i18n from "../i18n";
import Menu from "./Menu";
import { configContext, type ConfigContextValue } from "../ConfigContext";

describe("Menu", () => {
  beforeEach(() => {
    window.innerWidth = 375;
  });

  it("hides links by default and shows them after toggle", () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    const toggle = screen.getByRole("button", { name: i18n.t("app.menu") });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "Support" })).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const supportLink = screen.getByRole("link", { name: "Support" });
    expect(supportLink).toBeVisible();
    expect(supportLink).toHaveAttribute(
      "href",
      "/support",
    );
    expect(screen.getByRole("link", { name: "Logs" })).toBeVisible();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "Support" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Logs" })).not.toBeInTheDocument();
  });

  it("updates aria-expanded attribute when toggled", () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    const toggle = screen.getByRole("button", { name: i18n.t("app.menu") });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("shows support tabs on support route", () => {
    render(
      <MemoryRouter initialEntries={["/support"]}>
        <Menu />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByLabelText(i18n.t("app.menu")));
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
        market: true,
        owner: true,
        instrument: true,
        performance: true,
        transactions: true,
        screener: true,
        trading: true,
        timeseries: true,
        watchlist: true,
        allocation: true,
        rebalance: true,
        movers: true,
        instrumentadmin: true,
        dataadmin: true,
        virtual: true,
        support: false,
        settings: true,
        pension: true,
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
    fireEvent.click(screen.getByRole("button", { name: i18n.t("app.menu") }));
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
    const toggle = screen.getByRole("button", { name: i18n.t("app.menu") });
    fireEvent.click(toggle);
    const btn = screen.getByRole("button", { name: "Déconnexion" });
    fireEvent.click(btn);
    expect(onLogout).toHaveBeenCalled();
    i18n.changeLanguage("en");
  });
});
