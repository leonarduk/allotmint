import {
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useState, type ReactNode } from "react";
import userEvent from "@testing-library/user-event";

import MemberPage from "./Member";
import type { Portfolio } from "../types";
import { configContext, type AppConfig } from "../ConfigContext";
import useFetchWithRetry from "../hooks/useFetchWithRetry";
import { getPortfolio, listInstrumentGroups } from "../api";

vi.mock("../api", () => ({
  getPortfolio: vi.fn(),
  getOwners: vi.fn(),
  complianceForOwner: vi.fn().mockResolvedValue({ warnings: [] }),
  getValueAtRisk: vi.fn(),
  recomputeValueAtRisk: vi.fn(),
  getVarBreakdown: vi.fn(),
  listInstrumentGroups: vi.fn(),
  assignInstrumentGroup: vi.fn(),
  clearInstrumentGroup: vi.fn(),
  createInstrumentGroup: vi.fn(),
}));

vi.mock("../components/ValueAtRisk", () => ({
  __esModule: true,
  ValueAtRisk: () => <div data-testid="value-at-risk" />,
}));

vi.mock("../components/InstrumentTile", () => ({
  __esModule: true,
  default: ({ instrument }: { instrument: { ticker: string } }) => (
    <div data-testid="instrument-tile">{instrument.ticker}</div>
  ),
}));

vi.mock("../hooks/useFetchWithRetry", () => ({
  __esModule: true,
  default: vi.fn(),
}));

vi.mock("../RouteContext", async () => {
  const React = await import("react");
  return {
    useRoute: () => {
      const [selectedOwner, setSelectedOwner] = React.useState("");
      return {
        mode: "owner",
        setMode: () => {},
        selectedOwner,
        setSelectedOwner,
        selectedGroup: "",
        setSelectedGroup: () => {},
      };
    },
  };
});

const mockedFetchWithRetry = vi.mocked(useFetchWithRetry);
const mockGetPortfolio = vi.mocked(getPortfolio);
const mockListInstrumentGroups = vi.mocked(listInstrumentGroups);

const defaultConfig: AppConfig = {
  relativeViewEnabled: false,
  disabledTabs: [],
  tabs: {
    group: true,
    market: true,
    owner: true,
    instrument: true,
    performance: true,
    transactions: true,
    trading: true,
    screener: true,
    timeseries: true,
    watchlist: true,
    allocation: true,
    rebalance: true,
    movers: true,
    instrumentadmin: true,
    dataadmin: true,
    virtual: true,
    support: true,
    settings: true,
    profile: true,
    pension: true,
    reports: true,
    scenario: true,
    logs: true,
  },
  theme: "system",
  baseCurrency: "GBP",
};

const TestProvider = ({ children }: { children: ReactNode }) => {
  const [relativeViewEnabled, setRelativeViewEnabled] = useState(false);
  return (
    <configContext.Provider
      value={{
        ...defaultConfig,
        relativeViewEnabled,
        setRelativeViewEnabled,
        refreshConfig: async () => {},
        setBaseCurrency: () => {},
      }}
    >
      {children}
    </configContext.Provider>
  );
};

describe("Member page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedFetchWithRetry.mockReset();
    mockGetPortfolio.mockReset();
    mockListInstrumentGroups.mockReset();
    mockedFetchWithRetry.mockReturnValue({
      data: [
        {
          owner: "alice",
          accounts: ["ISA"],
        },
      ],
      loading: false,
      error: null,
      attempt: 0,
      maxAttempts: 5,
      unauthorized: false,
    });
    mockGetPortfolio.mockResolvedValue({
      owner: "alice",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 12345,
      accounts: [
        {
          account_type: "ISA",
          currency: "GBP",
          value_estimate_gbp: 12345,
          last_updated: "2024-01-01",
          holdings: [
            {
              ticker: "AAPL",
              name: "Apple Inc.",
              currency: "USD",
              units: 10,
              acquired_date: "2023-01-01",
              market_value_gbp: 2500,
              market_value_currency: "USD",
              gain_gbp: 500,
              gain_currency: "USD",
              gain_pct: 25,
              current_price_gbp: 250,
              instrument_type: "Stock",
            },
          ],
        },
      ],
    } as Portfolio);
    mockListInstrumentGroups.mockResolvedValue([]);
  });

  it("renders portfolio information when data loads", async () => {
    const router = createMemoryRouter(
      [
        {
          path: "/member/:owner",
          element: <MemberPage />,
        },
      ],
      { initialEntries: ["/member/alice"] },
    );

    render(
      <TestProvider>
        <RouterProvider router={router} />
      </TestProvider>,
    );

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alice"));

    expect(await screen.findByText(/Approx Total:/)).toBeInTheDocument();
    expect(screen.getByText(/ISA.*GBP/)).toBeInTheDocument();
  });

  it("renders the instrument table for the selected owner", async () => {
    const router = createMemoryRouter(
      [
        {
          path: "/member/:owner",
          element: <MemberPage />,
        },
      ],
      { initialEntries: ["/member/alice"] },
    );

    render(
      <TestProvider>
        <RouterProvider router={router} />
      </TestProvider>,
    );

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alice"));

    const holdingsHeading = await screen.findByRole("heading", {
      level: 2,
      name: "Holdings",
    });
    const holdingsSection = holdingsHeading.parentElement?.parentElement;
    expect(holdingsSection).toBeTruthy();
    const columnsContainer = within(holdingsSection as HTMLElement).getByText(
      /Columns:/i,
    );
    const instrumentTable = columnsContainer.nextElementSibling;
    expect(instrumentTable?.nodeName).toBe("TABLE");
    expect(
      within(instrumentTable as HTMLElement).getByRole("columnheader", {
        name: /Ticker/i,
      }),
    ).toBeInTheDocument();
    expect(
      within(holdingsSection as HTMLElement).getByLabelText(/Relative view/i),
    ).toBeInTheDocument();
  });

  it("shows the owner selector and reloads when the selection changes", async () => {
    mockedFetchWithRetry.mockReturnValue({
      data: [
        {
          owner: "alice",
          accounts: ["ISA"],
        },
        {
          owner: "bob",
          accounts: ["GIA"],
        },
      ],
      loading: false,
      error: null,
      attempt: 0,
      maxAttempts: 5,
      unauthorized: false,
    });

    const router = createMemoryRouter(
      [
        {
          path: "/member/:owner",
          element: <MemberPage />,
        },
      ],
      { initialEntries: ["/member/alice"] },
    );

    const user = userEvent.setup();

    render(
      <TestProvider>
        <RouterProvider router={router} />
      </TestProvider>,
    );

    const ownerSelector = await screen.findByLabelText(/Owner/i);
    expect(ownerSelector).toHaveValue("alice");

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alice"));

    await user.selectOptions(ownerSelector, "bob");

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("bob"));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/member/bob"),
    );
  });
});
