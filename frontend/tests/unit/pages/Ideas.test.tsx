import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import i18n from "@/i18n";
import Ideas from "@/pages/Ideas";
import { configContext, type ConfigContextValue } from "@/ConfigContext";

vi.mock("@/pages/Trading", () => ({
  default: () => <div data-testid="trading-signals" />,
}));
vi.mock("@/pages/Screener", () => ({
  Screener: () => <div data-testid="screener" />,
}));
vi.mock("@/pages/Watchlist", () => ({
  default: () => <div data-testid="watchlist" />,
}));

const baseConfig: ConfigContextValue = {
  relativeViewEnabled: false,
  disabledTabs: [],
  tabs: { trading: true, screener: true, watchlist: true },
  theme: "system",
  reportingCurrency: "GBP",
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
} as unknown as ConfigContextValue;

function renderIdeas(tab: "signals" | "screen" | "watchlist", config = baseConfig) {
  return render(
    <configContext.Provider value={config}>
      <MemoryRouter>
        <Ideas tab={tab} />
      </MemoryRouter>
    </configContext.Provider>,
  );
}

describe("Ideas page (#9852)", () => {
  it("mounts only the Signals tab on /trading", () => {
    renderIdeas("signals");
    expect(screen.getByTestId("trading-signals")).toBeInTheDocument();
    expect(screen.queryByTestId("screener")).toBeNull();
    expect(screen.getByText(i18n.t("ideas.explain.signals"))).toBeInTheDocument();
  });

  it("mounts only the Screen tab on /screener", () => {
    renderIdeas("screen");
    expect(screen.getByTestId("screener")).toBeInTheDocument();
    expect(screen.queryByTestId("trading-signals")).toBeNull();
    expect(screen.getByText(i18n.t("ideas.explain.screen"))).toBeInTheDocument();
  });

  it("links each tab to its own URL and marks the active one", () => {
    renderIdeas("screen");
    const nav = screen.getByRole("navigation", { name: i18n.t("ideas.tabsLabel") });
    const signals = screen.getByRole("link", { name: i18n.t("ideas.tabs.signals") });
    const screenTab = screen.getByRole("link", { name: i18n.t("ideas.tabs.screen") });
    expect(nav).toContainElement(signals);
    expect(signals).toHaveAttribute("href", "/trading");
    expect(signals).not.toHaveAttribute("aria-current");
    expect(screenTab).toHaveAttribute("href", "/screener");
    expect(screenTab).toHaveAttribute("aria-current", "page");
  });

  it("hides the tab bar when the other tabs are disabled", () => {
    renderIdeas("screen", {
      ...baseConfig,
      tabs: { ...baseConfig.tabs, trading: false, watchlist: false },
    });
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.getByTestId("screener")).toBeInTheDocument();
  });

  it("mounts the Watchlist as a third tab on /watchlist", () => {
    renderIdeas("watchlist");
    expect(screen.getByTestId("watchlist")).toBeInTheDocument();
    expect(screen.queryByTestId("screener")).toBeNull();
    const tab = screen.getByRole("link", { name: i18n.t("ideas.tabs.watchlist") });
    expect(tab).toHaveAttribute("href", "/watchlist");
    expect(tab).toHaveAttribute("aria-current", "page");
  });
});
