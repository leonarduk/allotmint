import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import i18n from "@/i18n";
import Menu from "@/components/Menu";
import { configContext, type ConfigContextValue } from "@/ConfigContext";

describe("Menu", () => {
  it("hides links by default and shows them after toggle", async () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    const settingsToggle = screen.getByRole("button", {
      name: i18n.t("app.menuCategories.preferences"),
    });
    expect(settingsToggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menuitem", { name: "Support" })).not.toBeInTheDocument();
    fireEvent.click(settingsToggle);
    expect(settingsToggle).toHaveAttribute("aria-expanded", "true");
    const supportLink = await screen.findByRole("menuitem", { name: "Support" });
    expect(supportLink).toBeVisible();
    expect(supportLink).toHaveAttribute(
      "href",
      "/support",
    );
    fireEvent.click(settingsToggle);
    expect(settingsToggle).toHaveAttribute("aria-expanded", "false");
    await waitFor(() =>
      expect(screen.queryByRole("menuitem", { name: "Support" })).not.toBeInTheDocument(),
    );
  });

  it("updates aria-expanded attribute when toggled", () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    const settingsToggle = screen.getByRole("button", {
      name: i18n.t("app.menuCategories.preferences"),
    });
    expect(settingsToggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(settingsToggle);
    expect(settingsToggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(settingsToggle);
    expect(settingsToggle).toHaveAttribute("aria-expanded", "false");
  });

  it("shows support tabs on support route", async () => {
    render(
      <MemoryRouter initialEntries={["/support"]}>
        <Menu />
      </MemoryRouter>,
    );
    const settingsToggle = screen.getByRole("button", {
      name: i18n.t("app.menuCategories.preferences"),
    });
    fireEvent.click(settingsToggle);
    const supportLink = await screen.findByRole("menuitem", { name: "Support" });
    expect(supportLink).toHaveAttribute("href", "/");
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
    const settingsToggle = screen.getByRole("button", {
      name: i18n.t("app.menuCategories.preferences"),
    });
    fireEvent.click(settingsToggle);
    expect(screen.queryByRole("menuitem", { name: "Support" })).toBeNull();
  });

  it("renders logout button when callback provided", async () => {
    const onLogout = vi.fn();
    i18n.changeLanguage("fr");
    render(
      <MemoryRouter>
        <Menu onLogout={onLogout} />
      </MemoryRouter>,
    );
    const settingsToggle = screen.getByRole("button", {
      name: i18n.t("app.menuCategories.preferences"),
    });
    fireEvent.click(settingsToggle);
    const btn = await screen.findByRole("menuitem", { name: "Déconnexion" });
    fireEvent.click(btn);
    expect(onLogout).toHaveBeenCalled();
    i18n.changeLanguage("en");
  });
});
