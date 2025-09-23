import { render, screen, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockGetConfig = vi.hoisted(() => vi.fn());
const mockUpdateConfig = vi.hoisted(() => vi.fn());
const mockGetOwners = vi.hoisted(() => vi.fn());
const mockSavePushSubscription = vi.hoisted(() => vi.fn());
const mockDeletePushSubscription = vi.hoisted(() => vi.fn());
const mockCheckPortfolioHealth = vi.hoisted(() => vi.fn());
const mockFetch = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
    API_BASE: "",
    getConfig: mockGetConfig,
    updateConfig: mockUpdateConfig,
    getOwners: mockGetOwners,
    savePushSubscription: mockSavePushSubscription,
    deletePushSubscription: mockDeletePushSubscription,
    checkPortfolioHealth: mockCheckPortfolioHealth,
    getCachedGroupInstruments: undefined,
}));

import Support from "@/pages/Support";
import en from "@/locales/en/translation.json";

async function expandSection(title: string) {
  const heading = await screen.findByRole("heading", { name: title });
  const trigger = within(heading.parentElement as HTMLElement).getByLabelText("Expand");
  await act(async () => {
    await userEvent.click(trigger);
  });
}

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
  mockFetch.mockResolvedValue({ ok: true, text: async () => "log entry" });
  vi.stubGlobal("fetch", mockFetch);
  mockGetConfig.mockResolvedValue({
    flag: true,
    theme: "system",
    tabs: {
      group: true,
      owner: true,
      instrument: true,
      trading: true,
      support: true,
      reports: true,
      allocation: false,
      scenario: false,
      market: true,
      rebalance: false,
      pension: true,
    },
  });
  mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Support page", () => {
  it("renders app link", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    const link = await screen.findByRole("link", { name: en.app.userLink });
    expect(link).toHaveAttribute("href", "/");
  });

  it("renders environment heading", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    expect(await screen.findByText(en.support.environment)).toBeInTheDocument();
  });

  it("shows owner selector", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.notifications.title);
    expect(
      await screen.findByLabelText(new RegExp(en.owner.label))
    ).toBeInTheDocument();
  });

  it("handles owner fetch failure gracefully", async () => {
    mockGetOwners.mockRejectedValueOnce(new Error("fail"));
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.notifications.title);
    const select = await screen.findByLabelText(new RegExp(en.owner.label));
    expect((select as HTMLSelectElement).options.length).toBe(0);
  });

  it("shows swagger link for VITE_API_URL", async () => {
    vi.stubEnv("VITE_API_URL", "http://localhost:8000");
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.environment);
    expect(
      await screen.findByRole("link", { name: "http://localhost:8000" })
    ).toHaveAttribute("href", "http://localhost:8000");
    expect(screen.getByRole("link", { name: "swagger" })).toHaveAttribute(
      "href",
      "http://localhost:8000/docs#/"
    );
    vi.unstubAllEnvs();
  });

  it("stringifies fresh config after saving", async () => {
  mockGetConfig.mockResolvedValueOnce({
    flag: true,
    theme: "system",
    tabs: {
      group: true,
      owner: true,
      instrument: true,
      trading: true,
      support: true,
      reports: true,
      allocation: false,
      scenario: false,
      market: true,
      rebalance: false,
      pension: true,
    },
  });
  mockGetConfig.mockResolvedValueOnce({
    flag: false,
    count: 5,
    theme: "dark",
    tabs: {
      group: true,
      owner: true,
      instrument: false,
      trading: true,
      support: true,
      reports: true,
      allocation: false,
      scenario: false,
      market: true,
      rebalance: false,
      pension: true,
    },
  });
    mockUpdateConfig.mockResolvedValue(undefined);

    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);

    const saveButton = await screen.findByRole("button", { name: en.support.config.save });
    await act(async () => {
      await userEvent.click(saveButton);
    });

    await screen.findByDisplayValue("5");

    const flagToggle = screen.getByRole("checkbox", { name: /flag/i });
    expect(flagToggle).not.toBeChecked();
    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
  });

  it("renders tab toggles and allows toggling", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);
    await screen.findByText(en.support.config.tabsEnabled);
    const instrument = await screen.findByRole("checkbox", {
      name: /^instrument$/i,
    });
    const support = screen.getByRole("checkbox", { name: /^support$/i });
    const group = screen.getByRole("checkbox", { name: /^group$/i });
    const owner = screen.getByRole("checkbox", { name: /^owner$/i });
    const allocation = screen.getByRole("checkbox", { name: /^allocation$/i });
    const market = screen.getByRole("checkbox", { name: /^market$/i });
    const rebalance = screen.getByRole("checkbox", { name: /^rebalance$/i });
    const pension = screen.getByRole("checkbox", { name: /^pension$/i });
    const scenario = screen.getByRole("checkbox", { name: /^scenario$/i });
    expect(instrument).toBeChecked();
    expect(support).toBeChecked();
    expect(group).toBeChecked();
    expect(owner).toBeChecked();
    expect(allocation).not.toBeChecked();
    expect(market).toBeChecked();
    expect(rebalance).not.toBeChecked();
    expect(pension).toBeChecked();
    expect(scenario).not.toBeChecked();
    await act(async () => {
      await userEvent.click(instrument);
    });
    await act(async () => {
      await userEvent.click(support);
    });
    expect(instrument).not.toBeChecked();
    expect(support).not.toBeChecked();
  });

  it("persists tab selections after save", async () => {
    mockGetConfig.mockResolvedValueOnce({
      flag: true,
      theme: "system",
      tabs: {
        group: true,
        owner: true,
        instrument: true,
      trading: true,
      support: true,
      reports: true,
      market: true,
        allocation: true,
        rebalance: true,
        pension: true,
      },
    });
    mockGetConfig.mockResolvedValueOnce({
      flag: true,
      theme: "system",
      tabs: {
        group: true,
        owner: true,
        instrument: false,
      trading: true,
      support: true,
      reports: true,
      market: true,
        allocation: true,
        rebalance: true,
        pension: true,
      },
    });
    mockUpdateConfig.mockResolvedValue(undefined);

    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);

    const instrument = await screen.findByRole("checkbox", {
      name: /^instrument$/i,
    });
    expect(instrument).toBeChecked();

    await act(async () => {
      await userEvent.click(instrument);
    });

    const saveButton = await screen.findByRole("button", { name: en.support.config.save });
    await act(async () => {
      await userEvent.click(saveButton);
    });

    expect(
      await screen.findByRole("checkbox", { name: /^instrument$/i })
    ).not.toBeChecked();
  });

  it("separates switches from other parameters", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);
    const switchesHeading = await screen.findByRole("heading", {
      name: en.support.config.otherSwitches,
    });
    const switchesSection = switchesHeading.parentElement as HTMLElement;
    expect(
      within(switchesSection).getByRole("checkbox", { name: /flag/i })
    ).toBeInTheDocument();
    expect(
      within(switchesSection).queryByRole("radio", { name: /dark/i })
    ).toBeNull();

    const paramsHeading = screen.getByRole("heading", {
      name: en.support.config.otherParams,
    });
    const paramsSection = paramsHeading.parentElement as HTMLElement;
    expect(
      within(paramsSection).getByRole("radio", { name: /dark/i })
    ).toBeInTheDocument();
    expect(
      within(paramsSection).queryByRole("checkbox", { name: /flag/i })
    ).toBeNull();
  });

  it("allows selecting theme via radio buttons", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);
    const dark = await screen.findByRole("radio", { name: "dark" });
    const light = screen.getByRole("radio", { name: "light" });
    await act(async () => {
      await userEvent.click(light);
    });
    expect(light).toBeChecked();
    await act(async () => {
      await userEvent.click(dark);
    });
    expect(dark).toBeChecked();
  });

  it("runs portfolio health check and shows findings", async () => {
    mockCheckPortfolioHealth.mockResolvedValue({
      findings: [
        { level: "warning", message: "foo", suggestion: "bar" },
      ],
    });
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.health.title);
    const btn = await screen.findByRole("button", {
      name: en.support.health.run,
    });
    await act(async () => {
      await userEvent.click(btn);
    });
    expect(await screen.findByText("foo")).toBeInTheDocument();
    expect(screen.getByText("bar")).toBeInTheDocument();
  });

  it("shows error when health check fails", async () => {
    mockCheckPortfolioHealth.mockRejectedValueOnce(new Error("fail"));
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.health.title);
    const btn = await screen.findByRole("button", {
      name: en.support.health.run,
    });
    await act(async () => {
      await userEvent.click(btn);
    });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(en.support.health.error);
  });

  it("loads logs and renders them", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.logs.title);
    expect(mockFetch).toHaveBeenCalledWith("/logs");
    expect(await screen.findByText("log entry")).toBeInTheDocument();
  });

  it("shows error message when logs fetch fails", async () => {
    mockFetch.mockRejectedValueOnce(new Error("fail"));
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.logs.title);
    expect(await screen.findByText(en.support.logs.error)).toBeInTheDocument();
    expect(screen.getByText(en.support.logs.empty)).toBeInTheDocument();
  });
});

