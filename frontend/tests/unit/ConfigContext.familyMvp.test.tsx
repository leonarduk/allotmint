import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfigProvider, useConfig } from "@/ConfigContext";

vi.mock("@/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/api")>();
  return {
    ...mod,
    getConfig: vi.fn(),
  };
});

function Probe() {
  const { tabs, disabledTabs } = useConfig();
  const disabledSet = new Set(disabledTabs ?? []);

  return (
    <div
      data-testid="config-probe"
      data-transactions={String(tabs.transactions)}
      data-trade-compliance={String(tabs["trade-compliance"])}
      data-trail={String(tabs.trail)}
      data-taxtools={String(tabs.taxtools)}
      data-reports={String(tabs.reports)}
      data-scenario={String(tabs.scenario)}
      data-disabled-transactions={String(disabledSet.has("transactions"))}
      data-disabled-trade-compliance={String(disabledSet.has("trade-compliance"))}
      data-disabled-reports={String(disabledSet.has("reports"))}
      data-disabled-scenario={String(disabledSet.has("scenario"))}
    />
  );
}

function expectFlag(probe: HTMLElement, attribute: string, expected: "true" | "false") {
  expect(probe.getAttribute(attribute)).toBe(expected);
}

describe("ConfigProvider Family MVP gating", () => {
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
      expectFlag(probe, "data-transactions", "false");
      expectFlag(probe, "data-trade-compliance", "false");
      expectFlag(probe, "data-trail", "false");
      expectFlag(probe, "data-taxtools", "false");
      expectFlag(probe, "data-reports", "false");
      expectFlag(probe, "data-scenario", "false");
      expectFlag(probe, "data-disabled-transactions", "true");
      expectFlag(probe, "data-disabled-trade-compliance", "true");
      expectFlag(probe, "data-disabled-reports", "true");
      expectFlag(probe, "data-disabled-scenario", "true");
    });
  });

  it("keeps optional feature tabs enabled when their Family MVP flags are enabled", async () => {
    const { getConfig } = await import("@/api");
    vi.mocked(getConfig).mockResolvedValue({
      enable_family_mvp: true,
      enable_compliance_workflows: true,
      enable_advanced_analytics: true,
      enable_reporting_extended: true,
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
      expectFlag(probe, "data-transactions", "false");
      expectFlag(probe, "data-trade-compliance", "true");
      expectFlag(probe, "data-trail", "true");
      expectFlag(probe, "data-taxtools", "true");
      expectFlag(probe, "data-reports", "true");
      expectFlag(probe, "data-scenario", "true");
      expectFlag(probe, "data-disabled-transactions", "true");
      expectFlag(probe, "data-disabled-trade-compliance", "false");
      expectFlag(probe, "data-disabled-reports", "false");
      expectFlag(probe, "data-disabled-scenario", "false");
    });
  });

  it("does not apply Family MVP forced disables when Family MVP is off", async () => {
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
      expectFlag(probe, "data-transactions", "true");
      expectFlag(probe, "data-trade-compliance", "true");
      expectFlag(probe, "data-trail", "true");
      expectFlag(probe, "data-taxtools", "true");
      expectFlag(probe, "data-reports", "true");
      expectFlag(probe, "data-scenario", "true");
      expectFlag(probe, "data-disabled-transactions", "false");
      expectFlag(probe, "data-disabled-trade-compliance", "false");
      expectFlag(probe, "data-disabled-reports", "false");
      expectFlag(probe, "data-disabled-scenario", "false");
    });
  });
});
