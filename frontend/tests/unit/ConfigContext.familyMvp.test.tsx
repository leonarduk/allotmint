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
  return (
    <div
      data-testid="config-probe"
      data-tabs={JSON.stringify(tabs)}
      data-disabled-tabs={JSON.stringify(disabledTabs ?? [])}
    />
  );
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
      const tabs = JSON.parse(probe.getAttribute("data-tabs") ?? "{}") as Record<string, boolean>;
      const disabledTabs = new Set(
        JSON.parse(probe.getAttribute("data-disabled-tabs") ?? "[]") as string[],
      );

      expect(tabs.transactions).toBe(false);
      expect(tabs["trade-compliance"]).toBe(false);
      expect(tabs.trail).toBe(false);
      expect(tabs.taxtools).toBe(false);
      expect(tabs.reports).toBe(false);
      expect(tabs.scenario).toBe(false);
      expect(disabledTabs.has("transactions")).toBe(true);
      expect(disabledTabs.has("trade-compliance")).toBe(true);
      expect(disabledTabs.has("reports")).toBe(true);
      expect(disabledTabs.has("scenario")).toBe(true);
    });
  });
});
