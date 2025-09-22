import { render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useState, type ReactNode } from "react";

import MemberPage from "./Member";
import type { Portfolio } from "../types";
import { configContext, type AppConfig } from "../ConfigContext";
import useFetchWithRetry from "../hooks/useFetchWithRetry";
import { getPortfolio } from "../api";

vi.mock("../api", () => ({
  getPortfolio: vi.fn(),
  getOwners: vi.fn(),
  complianceForOwner: vi.fn().mockResolvedValue({ warnings: [] }),
  getValueAtRisk: vi.fn(),
  recomputeValueAtRisk: vi.fn(),
  getVarBreakdown: vi.fn(),
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
          holdings: [],
        },
      ],
    } as Portfolio);
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
});
