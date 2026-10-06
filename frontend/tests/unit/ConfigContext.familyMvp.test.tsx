import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigProvider, parseReportingCurrency, useConfig } from "@/ConfigContext";

vi.mock("@/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/api")>();
  return {
    ...mod,
    getConfig: vi.fn(),
  };
});

function Probe() {
  const { tabs, disabledTabs, configLoaded } = useConfig();
  return (
    <div
      data-testid="config-probe"
      data-config-loaded={String(configLoaded)}
      data-tabs={JSON.stringify(tabs)}
      data-disabled-tabs={JSON.stringify(disabledTabs ?? [])}
    />
  );
}

function BaseCurrencyProbe() {
  const { reportingCurrency } = useConfig();
  return <div data-testid="base-currency-probe">{reportingCurrency}</div>;
}


function UnwrappedProbe() {
  const { configLoaded } = useConfig();
  return <div data-testid="unwrapped-config-loaded">{String(configLoaded)}</div>;
}

describe("ConfigProvider Family MVP gating", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("defaults to an unloaded config state outside the provider", () => {
    render(<UnwrappedProbe />);
    expect(screen.getByTestId("unwrapped-config-loaded").textContent).toBe("false");
  });

  it("disables non-MVP tabs by default when Family MVP mode is enabled", async () => {
    const { getConfig } = await import("@/api");
    vi.mocked(getConfig).mockResolvedValue({
      enable_family_mvp: true,
      enable_compliance_workflows: false,
      enable_advanced_analytics: false,
      enable_reporting_extended: false,
      tabs: {
        transactions: true,
        "trade-compliance": true,
        trail: true,
        taxtools: true,
        reports: true,
        scenario: true,
      },
    });

    render(
      <ConfigProvider>
        <Probe />
      </ConfigProvider>,
    );

    await waitFor(() => {
      const probe = screen.getByTestId("config-probe");
      const tabs = JSON.parse(probe.getAttribute("data-tabs") ?? "{}") as Record<string, boolean>;
      const disabledTabs = new Set(
        JSON.parse(probe.getAttribute("data-disabled-tabs") ?? "[]") as string[],
      );

      expect(probe.getAttribute("data-config-loaded")).toBe("true");
      // transactions stays enabled — Family MVP only force-disables the optional
      // feature tabs below; it does not gate the core transactions route.
      expect(tabs["trade-compliance"]).toBe(false);
      expect(tabs.trail).toBe(false);
      expect(tabs.taxtools).toBe(false);
      expect(tabs.reports).toBe(false);
      expect(tabs.scenario).toBe(false);
      expect(disabledTabs.has("trade-compliance")).toBe(true);
      expect(disabledTabs.has("reports")).toBe(true);
      expect(disabledTabs.has("scenario")).toBe(true);
    });
  });

  it("keeps optional feature tabs enabled when their Family MVP flags are explicitly enabled", async () => {
    const { getConfig } = await import("@/api");
    vi.mocked(getConfig).mockResolvedValue({
      enable_family_mvp: true,
      enable_compliance_workflows: true,
      enable_advanced_analytics: true,
      enable_reporting_extended: true,
      tabs: {
        "trade-compliance": true,
        trail: true,
        taxtools: true,
        reports: true,
        scenario: true,
      },
    });

    render(
      <ConfigProvider>
        <Probe />
      </ConfigProvider>,
    );

    await waitFor(() => {
      const probe = screen.getByTestId("config-probe");
      const tabs = JSON.parse(probe.getAttribute("data-tabs") ?? "{}") as Record<string, boolean>;
      const disabledTabs = new Set(
        JSON.parse(probe.getAttribute("data-disabled-tabs") ?? "[]") as string[],
      );

      expect(tabs["trade-compliance"]).toBe(true);
      expect(tabs.trail).toBe(true);
      expect(tabs.taxtools).toBe(true);
      expect(tabs.reports).toBe(true);
      expect(tabs.scenario).toBe(true);
      expect(disabledTabs.has("trade-compliance")).toBe(false);
      expect(disabledTabs.has("reports")).toBe(false);
      expect(disabledTabs.has("scenario")).toBe(false);
      // transactions stays enabled — Family MVP only force-disables the optional
      // feature tabs below; it does not gate the core transactions route.
    });
  });

  it("does not apply Family MVP forced tab disables when Family MVP is disabled", async () => {
    const { getConfig } = await import("@/api");
    vi.mocked(getConfig).mockResolvedValue({
      enable_family_mvp: false,
      tabs: {
        transactions: true,
        "trade-compliance": true,
        trail: true,
        taxtools: true,
        reports: true,
        scenario: true,
      },
    });

    render(
      <ConfigProvider>
        <Probe />
      </ConfigProvider>,
    );

    await waitFor(() => {
      const probe = screen.getByTestId("config-probe");
      const tabs = JSON.parse(probe.getAttribute("data-tabs") ?? "{}") as Record<string, boolean>;
      const disabledTabs = new Set(
        JSON.parse(probe.getAttribute("data-disabled-tabs") ?? "[]") as string[],
      );

      expect(tabs.transactions).toBe(true);
      expect(tabs["trade-compliance"]).toBe(true);
      expect(tabs.trail).toBe(true);
      expect(tabs.taxtools).toBe(true);
      expect(tabs.reports).toBe(true);
      expect(tabs.scenario).toBe(true);
      expect(disabledTabs.has("transactions")).toBe(false);
      expect(disabledTabs.has("trade-compliance")).toBe(false);
      expect(disabledTabs.has("reports")).toBe(false);
      expect(disabledTabs.has("scenario")).toBe(false);
    });
  });

  it("reports in the configured base currency and ignores a stale stored one (#9753, #9768)", async () => {
    const { getConfig } = await import("@/api");
    vi.mocked(getConfig).mockResolvedValue({
      enable_family_mvp: true,
      base_currency: " usd ",
      tabs: {},
    });
    localStorage.setItem("baseCurrency", "EUR");

    render(
      <ConfigProvider>
        <BaseCurrencyProbe />
      </ConfigProvider>,
    );

    // GBP until /config says otherwise; the stale browser value is never used.
    expect(screen.getByTestId("base-currency-probe").textContent).toBe("GBP");
    await waitFor(() =>
      expect(screen.getByTestId("base-currency-probe").textContent).toBe("USD"),
    );
    expect(localStorage.getItem("baseCurrency")).toBeNull();
  });

  it.each([
    [undefined, "GBP"],
    [null, "GBP"],
    ["", "GBP"],
    ["GBX", "GBP"],
    ["gbp", "GBP"],
    ["dollars", "GBP"],
    ["eur", "EUR"],
  ])("parses base_currency %s as %s", (raw, expected) => {
    expect(parseReportingCurrency(raw)).toBe(expected);
  });

  it("marks config as loaded when config fetch fails", async () => {
    const { getConfig } = await import("@/api");
    vi.mocked(getConfig).mockRejectedValue(new Error("boom"));

    render(
      <ConfigProvider>
        <Probe />
      </ConfigProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("config-probe").getAttribute("data-config-loaded")).toBe("true");
    });
  });
});
