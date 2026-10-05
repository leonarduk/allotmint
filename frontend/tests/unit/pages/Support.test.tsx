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
const mockRefreshPrices = vi.hoisted(() => vi.fn());
const mockGetRefreshPricesProgress = vi.hoisted(() => vi.fn());
const mockGetMcpTools = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    API_BASE: "",
    getConfig: mockGetConfig,
    updateConfig: mockUpdateConfig,
    getOwners: mockGetOwners,
    savePushSubscription: mockSavePushSubscription,
    deletePushSubscription: mockDeletePushSubscription,
    checkPortfolioHealth: mockCheckPortfolioHealth,
    refreshPrices: mockRefreshPrices,
    getRefreshPricesProgress: mockGetRefreshPricesProgress,
    getMcpTools: mockGetMcpTools,
  };
});

import Support from "@/pages/Support";
import en from "@/locales/en/translation.json";
import { setAuthToken, UNAUTHORIZED_EVENT } from "@/api";

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
  setAuthToken(null);
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
  mockGetMcpTools.mockResolvedValue({
    tools: [
      { name: "get_portfolio", description: "Portfolio", enabled: true },
      { name: "read_data_file", description: "Read a file", enabled: true },
    ],
    mcp_error: null,
  });
  mockRefreshPrices.mockResolvedValue({ status: "ok", tickers: 0 });
  mockGetRefreshPricesProgress.mockResolvedValue({
    running: false,
    total: 0,
    completed: 0,
    current_ticker: null,
  });
});

afterEach(() => {
  window.history.replaceState(null, "", window.location.pathname);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Support page", () => {
  it("renders app link", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    const link = await screen.findByRole("link", { name: en.app.userLink });
    expect(link).toHaveAttribute("href", "/");
  });

  it("opens the local login override for its direct link", async () => {
    window.history.replaceState(null, "", "#local-login-override");
    render(<Support />, { wrapper: MemoryRouter });

    expect(
      await screen.findByLabelText(en.support.localLogin.label),
    ).toBeVisible();
  });

  it("renders environment heading", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    expect(await screen.findByText(en.support.environment)).toBeInTheDocument();
  });

  it("links to the Data Explorer (issue #6058)", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.dataExplorer.title);
    const link = await screen.findByRole("link", {
      name: en.support.dataExplorer.link,
    });
    expect(link).toHaveAttribute("href", "/data-explorer");
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
    vi.stubEnv("VITE_API_URL", "http://localhost:6468");
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.environment);
    expect(
      await screen.findByRole("link", { name: "http://localhost:6468" })
    ).toHaveAttribute("href", "http://localhost:6468");
    expect(screen.getByRole("link", { name: "API Console" })).toHaveAttribute(
      "href",
      "http://localhost:6468/api-console"
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

  it("saves the dataquality tab toggle and persists it after save", async () => {
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
        allocation: true,
        scenario: true,
        market: true,
        rebalance: true,
        pension: true,
        dataquality: false,
      },
    });
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
        allocation: true,
        scenario: true,
        market: true,
        rebalance: true,
        pension: true,
        dataquality: true,
      },
    });
    mockUpdateConfig.mockResolvedValue(undefined);

    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);

    const dataquality = await screen.findByRole("checkbox", {
      name: /^dataquality$/i,
    });
    expect(dataquality).not.toBeChecked();

    await act(async () => {
      await userEvent.click(dataquality);
    });
    expect(dataquality).toBeChecked();

    const saveButton = screen.getByRole("button", {
      name: en.support.config.save,
    });
    await act(async () => {
      await userEvent.click(saveButton);
    });

    expect(mockUpdateConfig).toHaveBeenCalledWith(
      expect.objectContaining({
        ui: expect.objectContaining({
          tabs: expect.objectContaining({ dataquality: true }),
        }),
      }),
    );

    expect(
      await screen.findByText(en.support.status.saved),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("checkbox", { name: /^dataquality$/i }),
    ).toBeChecked();
  });

  it("saves only the fields that changed, not the whole resolved config (#7896)", async () => {
    mockGetConfig.mockResolvedValue({
      flag: true,
      count: 5,
      theme: "system",
      data_root: "C:\\Users\\someone\\allotmint-data",
      error_summary: { enabled: true },
      tabs: { group: true, owner: true },
    });
    mockUpdateConfig.mockResolvedValue(undefined);

    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);

    const count = await screen.findByDisplayValue("5");
    await act(async () => {
      await userEvent.clear(count);
      await userEvent.type(count, "7");
    });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: en.support.config.save }));
    });

    // No untouched resolved paths, no "[object Object]", no unchanged tabs.
    expect(mockUpdateConfig).toHaveBeenCalledWith({ count: 7 });
  });

  it("lists MCP tools, all on, and saves a switched-off tool under the mcp section", async () => {
    mockUpdateConfig.mockResolvedValue(undefined);
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);

    expect(await screen.findByRole("heading", { name: en.support.config.mcpTools })).toBeInTheDocument();
    const readFile = await screen.findByLabelText("read_data_file");
    expect(readFile).toBeChecked();
    expect(screen.getByLabelText("get_portfolio")).toBeChecked();

    await act(async () => {
      await userEvent.click(readFile);
    });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: en.support.config.save }));
    });

    expect(mockUpdateConfig).toHaveBeenCalledWith({
      mcp: { mcp_tools: { get_portfolio: true, read_data_file: false } },
    });
  });

  it("does not send MCP switches when none changed", async () => {
    mockUpdateConfig.mockResolvedValue(undefined);
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);
    await screen.findByLabelText("read_data_file");

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: en.support.config.save }));
    });

    expect(mockUpdateConfig).toHaveBeenCalledWith({});
  });

  it("edits mcp_github_repo as an ordinary config parameter", async () => {
    mockGetConfig.mockResolvedValue({
      theme: "system",
      mcp_github_repo: "octo/tracker",
      mcp_tools: { read_data_file: false },
      tabs: { group: true },
    });
    mockUpdateConfig.mockResolvedValue(undefined);
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);

    const repo = await screen.findByDisplayValue("octo/tracker");
    await act(async () => {
      await userEvent.clear(repo);
      await userEvent.type(repo, "octo/new-repo");
    });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: en.support.config.save }));
    });

    // The mcp_tools map is never echoed back from the generic form.
    expect(mockUpdateConfig).toHaveBeenCalledWith({ mcp_github_repo: "octo/new-repo" });
  });

  it("shows why the MCP tool list is incomplete", async () => {
    mockGetMcpTools.mockResolvedValue({ tools: [], mcp_error: "MCP_SERVER_URL is not set" });
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);

    expect(await screen.findByText("MCP_SERVER_URL is not set")).toBeInTheDocument();
  });

  it("marks an MCP tool the server reports as not configured, keeping its switch", async () => {
    const reason = "Web search is not configured: set ALLOTMINT_MCP_BRAVE_API_KEY to a Brave Search API key.";
    mockGetMcpTools.mockResolvedValue({
      tools: [
        { name: "get_portfolio", description: "Portfolio", enabled: true, not_configured: null },
        { name: "search_web", description: "Search", enabled: true, not_configured: reason },
      ],
      mcp_error: null,
    });
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);

    const searchWeb = await screen.findByLabelText("search_web");
    expect(searchWeb).toBeChecked();
    expect(searchWeb).toHaveAccessibleDescription(
      `${en.support.config.mcpToolNotConfigured}: ${reason} ${en.support.config.mcpToolSetupLink}`,
    );
    const setupLinks = screen.getAllByRole("link", { name: en.support.config.mcpToolSetupLink });
    expect(setupLinks).toHaveLength(1);
    expect(setupLinks[0]).toHaveAttribute(
      "href",
      "https://github.com/leonarduk/allotmint/blob/main/docs/CONTRIBUTOR_RUNBOOK.md#running-the-chat-mcp-agent-locally",
    );
    expect(setupLinks[0]).toHaveAttribute("target", "_blank");
    expect(setupLinks[0]).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByLabelText("get_portfolio")).not.toHaveAccessibleDescription();
    expect(screen.getAllByText(new RegExp(en.support.config.mcpToolNotConfigured))).toHaveLength(1);
    // The note's id comes from the tool name, not its list position.
    expect(searchWeb).toHaveAttribute("aria-describedby", "mcp-tool-status-search_web");
  });

  it("derives a safe note id from MCP tool names with characters invalid in an id", async () => {
    mockGetMcpTools.mockResolvedValue({
      tools: [
        { name: "web search.v2", description: "Search", enabled: true, not_configured: "missing key" },
      ],
      mcp_error: null,
    });
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.config.title);

    const tool = await screen.findByLabelText("web search.v2");
    expect(tool).toHaveAttribute("aria-describedby", "mcp-tool-status-web-search-v2");
    expect(tool).toHaveAccessibleDescription(
      `${en.support.config.mcpToolNotConfigured}: missing key ${en.support.config.mcpToolSetupLink}`,
    );
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
    const call = mockFetch.mock.calls.find(([url]) =>
      String(url).endsWith("/logs"),
    );
    expect(call).toBeDefined();
    expect(await screen.findByText("log entry")).toBeInTheDocument();
  });

  it("sends the Authorization header when loading logs (issue #6111)", async () => {
    setAuthToken("test-logs-token");
    try {
      render(<Support />, { wrapper: MemoryRouter });
      await expandSection(en.support.logs.title);
      await screen.findByText("log entry");
      const call = mockFetch.mock.calls.find(([url]) =>
        String(url).endsWith("/logs"),
      );
      expect(call).toBeDefined();
      const headers = call?.[1]?.headers as Headers;
      expect(headers.get("Authorization")).toBe("Bearer test-logs-token");
    } finally {
      setAuthToken(null);
    }
  });

  it("shows error message when logs fetch fails", async () => {
    mockFetch.mockRejectedValueOnce(new Error("fail"));
    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.logs.title);
    expect(await screen.findByText(en.support.logs.error)).toBeInTheDocument();
    expect(screen.getByText(en.support.logs.empty)).toBeInTheDocument();
  });

  it("surfaces a 401 on the logs endpoint as an error state, not silently (issue #6111)", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () => Promise.resolve({ detail: "Session expired" }),
    });
    const handler = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    try {
      render(<Support />, { wrapper: MemoryRouter });
      await expandSection(en.support.logs.title);
      expect(await screen.findByText(en.support.logs.error)).toBeInTheDocument();
      expect(screen.getByText(en.support.logs.empty)).toBeInTheDocument();
      expect(handler).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(UNAUTHORIZED_EVENT, handler);
    }
  });

  it("shows incremental progress while refreshing prices, not just a static label (#8015)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    let resolveRefresh: (v: { status: string; tickers: number }) => void;
    mockRefreshPrices.mockReturnValue(
      new Promise((resolve) => {
        resolveRefresh = resolve;
      }),
    );
    mockGetRefreshPricesProgress.mockResolvedValue({
      running: true,
      total: 47,
      completed: 12,
      current_ticker: "AAPL.L",
    });

    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.priceRefresh);

    const btn = await screen.findByRole("button", { name: en.app.refreshPrices });
    await act(async () => {
      await userEvent.click(btn);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(
      await screen.findByRole("button", {
        name: "Refreshing… (12/47)",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Fetching AAPL.L…")).toBeInTheDocument();

    await act(async () => {
      resolveRefresh!({ status: "ok", tickers: 47 });
      await Promise.resolve();
    });

    expect(
      await screen.findByRole("button", { name: en.app.refreshPrices }),
    ).toBeInTheDocument();
  });

  it("falls back to the static refreshing label when progress polling fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    let resolveRefresh: (v: { status: string; tickers: number }) => void;
    mockRefreshPrices.mockReturnValue(
      new Promise((resolve) => {
        resolveRefresh = resolve;
      }),
    );
    mockGetRefreshPricesProgress.mockRejectedValue(new Error("network error"));

    render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.priceRefresh);

    const btn = await screen.findByRole("button", { name: en.app.refreshPrices });
    await act(async () => {
      await userEvent.click(btn);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(
      await screen.findByRole("button", { name: en.app.refreshing }),
    ).toBeInTheDocument();

    await act(async () => {
      resolveRefresh!({ status: "ok", tickers: 0 });
      await Promise.resolve();
    });

    expect(
      await screen.findByRole("button", { name: en.app.refreshPrices }),
    ).toBeInTheDocument();
  });

  it("stops polling for progress once the component unmounts mid-refresh", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    mockRefreshPrices.mockReturnValue(new Promise(() => {})); // never resolves
    mockGetRefreshPricesProgress.mockResolvedValue({
      running: true,
      total: 10,
      completed: 1,
      current_ticker: "AAPL.L",
    });

    const { unmount } = render(<Support />, { wrapper: MemoryRouter });
    await expandSection(en.support.priceRefresh);

    const btn = await screen.findByRole("button", { name: en.app.refreshPrices });
    await act(async () => {
      await userEvent.click(btn);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    const callsBeforeUnmount = mockGetRefreshPricesProgress.mock.calls.length;
    expect(callsBeforeUnmount).toBeGreaterThan(0);

    unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(mockGetRefreshPricesProgress.mock.calls.length).toBe(callsBeforeUnmount);
  });
});
