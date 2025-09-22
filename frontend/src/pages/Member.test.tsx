import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { describe, beforeEach, it, expect, vi } from "vitest";

import { RouteProvider } from "../RouteContext";
import Member from "./Member";
import type {
  ComplianceResult,
  Portfolio,
  ValueAtRiskResponse,
  VarBreakdown,
} from "../types";
import * as api from "../api";

vi.mock("../api", () => ({
  getOwners: vi.fn(),
  getPortfolio: vi.fn(),
  getGroups: vi.fn(),
  complianceForOwner: vi.fn(),
  getValueAtRisk: vi.fn(),
  recomputeValueAtRisk: vi.fn(),
  getVarBreakdown: vi.fn(),
}));

const mockGetOwners = vi.mocked(api.getOwners);
const mockGetPortfolio = vi.mocked(api.getPortfolio);
const mockGetGroups = vi.mocked(api.getGroups);
const mockComplianceForOwner = vi.mocked(api.complianceForOwner);
const mockGetValueAtRisk = vi.mocked(api.getValueAtRisk);
const mockRecomputeValueAtRisk = vi.mocked(api.recomputeValueAtRisk);
const mockGetVarBreakdown = vi.mocked(api.getVarBreakdown);

function createPortfolio(owner: string): Portfolio {
  return {
    owner,
    as_of: "2024-01-01",
    trades_this_month: 0,
    trades_remaining: 0,
    total_value_estimate_gbp: 0,
    accounts: [],
  };
}

describe("Member page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetGroups.mockResolvedValue([]);
    mockGetOwners.mockResolvedValue([
      { owner: "alice", accounts: [] },
      { owner: "bob", accounts: [] },
    ]);
    mockGetPortfolio.mockImplementation(async (owner: string) =>
      createPortfolio(owner),
    );
    mockComplianceForOwner.mockResolvedValue({
      owner: "",
      warnings: [],
      trade_counts: {},
    } satisfies ComplianceResult);
    mockGetValueAtRisk.mockResolvedValue({
      owner: "",
      as_of: "2024-01-01",
      var: {},
    } satisfies ValueAtRiskResponse);
    mockRecomputeValueAtRisk.mockResolvedValue({ owner: "", var: {} });
    mockGetVarBreakdown.mockResolvedValue([] satisfies VarBreakdown[]);
  });

  function renderMember(initialPath = "/member/alice") {
    window.history.pushState({}, "", initialPath);
    const router = createMemoryRouter(
      [
        {
          path: "/member/:owner?",
          element: (
            <RouteProvider>
              <Member />
            </RouteProvider>
          ),
        },
      ],
      { initialEntries: [initialPath] },
    );
    render(<RouterProvider router={router} />);
    return router;
  }

  it("renders the owner selector with options from the API", async () => {
    renderMember();

    const select = await screen.findByLabelText(/owner/i, {
      selector: "select",
    });

    await waitFor(() => expect(select).toHaveValue("alice"));

    const options = within(select).getAllByRole("option");
    expect(options.map((opt) => opt.value)).toEqual(["alice", "bob"]);
  });

  it("reloads the portfolio when the selected owner changes", async () => {
    const router = renderMember();
    const user = userEvent.setup();

    const select = await screen.findByLabelText(/owner/i, {
      selector: "select",
    });

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alice"));
    mockGetPortfolio.mockClear();

    await user.selectOptions(select, "bob");

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("bob"));
    expect(router.state.location.pathname).toBe("/member/bob");
  });
});
