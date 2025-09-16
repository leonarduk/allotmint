import { render, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, afterEach } from "vitest";
import i18n from "../i18n";
import Menu from "./Menu";
import { configContext, type ConfigContextValue } from "../ConfigContext";

afterEach(cleanup);

describe("Menu", () => {
  it("hides links by default and shows them after toggle", () => {
    const { getByRole, getByLabelText } = render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    const nav = getByRole("navigation");
    const container = nav.querySelector(":scope > div") as HTMLElement | null;
    expect(container).not.toBeNull();
    const menuContainer = container as HTMLElement;
    expect(menuContainer).toHaveClass("hidden");
    const toggle = getByLabelText(i18n.t("app.menu"));
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(menuContainer).toHaveClass("flex");
    expect(getByRole("link", { name: "Support" })).toHaveAttribute(
      "href",
      "/support",
    );
    expect(getByRole("link", { name: "Logs" })).toHaveAttribute("href", "/logs");
  });

  it("shows support tabs on support route", () => {
    const { getByLabelText, getByRole } = render(
      <MemoryRouter initialEntries={["/support"]}>
        <Menu />
      </MemoryRouter>,
    );
    fireEvent.click(getByLabelText(i18n.t("app.menu")));
    expect(getByRole("link", { name: "Logs" })).toBeInTheDocument();
    expect(getByRole("link", { name: "Support" })).toHaveAttribute(
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
        profile: false,
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
    const { queryByRole } = render(
      <configContext.Provider value={config}>
        <MemoryRouter>
          <Menu />
        </MemoryRouter>
      </configContext.Provider>,
    );
    expect(queryByRole("link", { name: "Support" })).toBeNull();
  });

  it("renders logout button when callback provided", () => {
    const onLogout = vi.fn();
    i18n.changeLanguage("fr");
    const { getByLabelText, getByRole } = render(
      <MemoryRouter>
        <Menu onLogout={onLogout} />
      </MemoryRouter>,
    );
    const toggle = getByLabelText(i18n.t("app.menu"));
    fireEvent.click(toggle);
    fireEvent.click(getByLabelText(i18n.t("app.menu")));
    const btn = getByRole("button", { name: "Déconnexion" });
    fireEvent.click(btn);
    expect(onLogout).toHaveBeenCalled();
    i18n.changeLanguage("en");
  });
});
