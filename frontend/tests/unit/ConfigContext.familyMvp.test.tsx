import { useEffect } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigProvider, useConfig } from "@/ConfigContext";

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

function BaseCurrencySetter() {
  const { baseCurrency, setBaseCurrency } = useConfig();
  useEffect(() => {
    setBaseCurrency("USD");
  }, [setBaseCurrency]);
  return <div data-testid="base-currency-probe">{baseCurrency}</div>;
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
      expect(tabs.transactions).toBe(true);
      expect(tabs["trade-compliance"]).toBe(false);
      expect(tabs.trail).toBe(false);
      expect(tabs.taxtools).toBe(false);
      expect(tabs.reports).toBe(false);
      expect(tabs.scenario).toBe(false);
      expect(disabledTabs.has("transactions")).toBe(false);
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
      expect(tabs.transactions).toBe(true);
      expect(disabledTabs.has("transactions")).toBe(false);
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

  it("does not refetch config when base currency changes locally", async () => {
    const { getConfig } = await import("@/api");
    vi.mocked(getConfig).mockResolvedValue({
      enable_family_mvp: true,
      tabs: {},
    });

    render(
      <ConfigProvider>
        <BaseCurrencySetter />
      </ConfigProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("base-currency-probe").textContent).toBe("USD");
    });
    expect(vi.mocked(getConfig)).toHaveBeenCalledTimes(1);
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
