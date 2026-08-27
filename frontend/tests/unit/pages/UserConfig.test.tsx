import { render, screen, act, waitFor, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach, vi } from "vitest";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetUserConfig = vi.hoisted(() => vi.fn());
const mockGetApprovals = vi.hoisted(() => vi.fn());
const mockUpdateUserConfig = vi.hoisted(() => vi.fn());
const mockAddApproval = vi.hoisted(() => vi.fn());
const mockRemoveApproval = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  API_BASE: "",
  getOwners: mockGetOwners,
  getUserConfig: mockGetUserConfig,
  getApprovals: mockGetApprovals,
  updateUserConfig: mockUpdateUserConfig,
  addApproval: mockAddApproval,
  removeApproval: mockRemoveApproval,
}));

import UserConfig from "@/pages/UserConfig";
import { AuthContext } from "@/AuthContext";

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
});

describe("UserConfig page", () => {
  it("handles non-array config values", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({
      approval_exempt_tickers: "ABC",
      approval_exempt_types: null,
    });
    mockGetApprovals.mockResolvedValue({ approvals: [] });
    mockUpdateUserConfig.mockResolvedValue(undefined);

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    const inputs = await screen.findAllByRole("textbox");
    expect((inputs[0] as HTMLInputElement).value).toBe("");
    expect((inputs[1] as HTMLInputElement).value).toBe("");

    const saveButton = screen.getByRole("button", { name: /save/i });
    await act(async () => {
      await userEvent.click(saveButton);
    });
    expect(mockUpdateUserConfig).toHaveBeenCalledWith("alex", {
      approval_exempt_tickers: [],
      approval_exempt_types: null,
    });
  });

  it("defaults the owner dropdown to the logged-in user's owner", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [], email: "alex@example.com" },
      { owner: "jamie", accounts: [], email: "jamie@example.com" },
    ]);
    mockGetUserConfig.mockResolvedValue({});
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(
      <AuthContext.Provider
        value={{ user: { email: "jamie@example.com" }, setUser: vi.fn() }}
      >
        <UserConfig />
      </AuthContext.Provider>,
    );

    const select = await screen.findByRole("combobox");
    await screen.findByDisplayValue("jamie");
    expect((select as HTMLSelectElement).value).toBe("jamie");
    // The config-fetch effect must run for the mapped owner, not "" or the
    // first owner: proves the owner-default and config-fetch effects sequence
    // correctly (the owner change re-triggers the fetch).
    await waitFor(() =>
      expect(mockGetUserConfig).toHaveBeenCalledWith("jamie"),
    );
    expect(mockGetUserConfig).not.toHaveBeenCalledWith("");
    expect(mockGetUserConfig).not.toHaveBeenCalledWith("alex");
  });

  it("defaults the owner dropdown to the app-wide active owner (#5553)", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [], email: "alex@example.com" },
      { owner: "jamie", accounts: [], email: "jamie@example.com" },
    ]);
    mockGetUserConfig.mockResolvedValue({});
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(
      <AuthContext.Provider
        value={{ user: { email: "jamie@example.com" }, setUser: vi.fn() }}
      >
        <UserConfig selectedOwner="alex" />
      </AuthContext.Provider>,
    );

    const select = await screen.findByRole("combobox");
    await screen.findByDisplayValue("alex");
    expect((select as HTMLSelectElement).value).toBe("alex");
    // The globally active owner (e.g. shown in the top nav) must win over the
    // logged-in user's mapped owner so Settings reflects what the rest of the
    // app is already showing, instead of silently switching to a different
    // account.
    await waitFor(() => expect(mockGetUserConfig).toHaveBeenCalledWith("alex"));
    expect(mockGetUserConfig).not.toHaveBeenCalledWith("jamie");
  });

  it("falls back to the logged-in user's owner when the active owner isn't in the authorized list (#5553)", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [], email: "alex@example.com" },
      { owner: "jamie", accounts: [], email: "jamie@example.com" },
    ]);
    mockGetUserConfig.mockResolvedValue({});
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(
      <AuthContext.Provider
        value={{ user: { email: "jamie@example.com" }, setUser: vi.fn() }}
      >
        <UserConfig selectedOwner="not-a-real-owner" />
      </AuthContext.Provider>,
    );

    const select = await screen.findByRole("combobox");
    await screen.findByDisplayValue("jamie");
    expect((select as HTMLSelectElement).value).toBe("jamie");
  });

  it("leaves the owner dropdown unselected when there is no logged-in user", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [], email: "alex@example.com" },
      { owner: "jamie", accounts: [], email: "jamie@example.com" },
    ]);
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    expect((select as HTMLSelectElement).value).toBe("");
  });

  it("prompts the user to pick an owner instead of showing empty space when none resolves (#7224)", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [], email: "alex@example.com" },
      { owner: "jamie", accounts: [], email: "jamie@example.com" },
    ]);
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(<UserConfig />);

    await screen.findByRole("combobox");
    const prompt = await screen.findByRole("status");
    expect(prompt).toHaveTextContent(
      /select an account holder to view their settings/i,
    );
    // The trading-rule fields and Approvals table must stay hidden until an
    // owner is chosen -- the prompt replaces empty space, not the fields.
    expect(screen.queryByText(/min hold days/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("does not show the owner prompt while owners are still loading (#7224)", async () => {
    let resolveOwners: (value: unknown) => void = () => {};
    mockGetOwners.mockReturnValue(
      new Promise((resolve) => {
        resolveOwners = resolve;
      }),
    );
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(<UserConfig />);

    // While owners are still in flight there is no owner list to prompt
    // against yet -- the loading message owns this state, not the prompt.
    expect(screen.getByText(/loading owners/i)).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    await act(async () => {
      resolveOwners([{ owner: "alex", accounts: [] }]);
    });

    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("renders the Trading Rules title instead of the stale User Settings name (#7224)", async () => {
    mockGetOwners.mockResolvedValue([]);
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(<UserConfig />);

    expect(
      await screen.findByRole("heading", { level: 1, name: /trading rules/i }),
    ).toBeInTheDocument();
  });

  it("hides the owner prompt once an owner is selected and labels fields with units (#7224)", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({});
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    // getByLabelText (not getByText) proves the <label> is actually
    // associated with its <input> via htmlFor/id, not just visually adjacent.
    expect(
      screen.getByLabelText(/min hold days \(days\)/i),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/max trades \/ month \(trades\)/i),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/approval exempt tickers \(comma-separated\)/i),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/approval exempt types \(comma-separated\)/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/newly bought position must be held before it can be sold/i),
    ).toBeInTheDocument();
    // Max Trades / Month must describe the calendar-month reset the backend
    // actually implements (backend/common/portfolio.py: d.month == today.month),
    // not a rolling window.
    expect(
      screen.getByText(/current calendar month; resets on the 1st/i),
    ).toBeInTheDocument();
    // Exempt types must carry the commodity-ETF carve-out from
    // backend/common/holding_utils.py (is_etf and is_commodity forces
    // exempt_type back to False).
    expect(
      screen.getByText(/except commodity etfs, which always require approval/i),
    ).toBeInTheDocument();
    // Approvals must explain expiry (backend/common/approvals.py:
    // is_approval_valid), not just "the date they were approved".
    expect(
      screen.getByText(/expires the same day it's granted/i),
    ).toBeInTheDocument();
  });

  it("shows a loading indicator while the authorized owners are being fetched", async () => {
    let resolveOwners: (value: unknown) => void = () => {};
    mockGetOwners.mockReturnValue(
      new Promise((resolve) => {
        resolveOwners = resolve;
      }),
    );
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(<UserConfig />);

    expect(screen.getByText(/loading owners/i)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();

    await act(async () => {
      resolveOwners([{ owner: "alex", accounts: [] }]);
    });

    expect(await screen.findByRole("combobox")).toBeInTheDocument();
    expect(screen.queryByText(/loading owners/i)).not.toBeInTheDocument();
  });

  it("shows a meaningful empty state when the user has no authorized owners", async () => {
    mockGetOwners.mockResolvedValue([]);
    mockGetApprovals.mockResolvedValue({ approvals: [] });

    render(<UserConfig />);

    expect(await screen.findByText(/no accounts are available/i)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("shows a permission-specific message when loading approvals 403s (#5215)", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({});
    const forbidden = new Error("HTTP 403 - Forbidden (/accounts/alex/approvals)");
    (forbidden as any).status = 403;
    mockGetApprovals.mockRejectedValue(forbidden);

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    expect(
      await screen.findByText(/don't have permission to view or manage approvals/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Failed to load approvals$/)).not.toBeInTheDocument();
  });

  it("shows a session-expiry message when loading approvals 401s (#5215)", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({});
    const unauthorized = new Error("HTTP 401 - Unauthorized (/accounts/alex/approvals)");
    (unauthorized as any).status = 401;
    mockGetApprovals.mockRejectedValue(unauthorized);

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    expect(await screen.findByText(/session has expired/i)).toBeInTheDocument();
  });

  it("shows a permission-specific message when adding an approval 403s (#5215)", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({});
    mockGetApprovals.mockResolvedValue({ approvals: [] });
    const forbidden = new Error("HTTP 403 - Forbidden (/accounts/alex/approvals)");
    (forbidden as any).status = 403;
    mockAddApproval.mockRejectedValue(forbidden);

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    const tickerInput = await screen.findByPlaceholderText("Ticker");
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement;
    await act(async () => {
      await userEvent.type(tickerInput, "ABC");
      fireEvent.change(dateInput, { target: { value: "2024-01-01" } });
    });
    const addButton = screen.getByRole("button", { name: /add/i });
    await act(async () => {
      await userEvent.click(addButton);
    });

    expect(
      await screen.findByText(/don't have permission to view or manage approvals/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Failed to add approval$/)).not.toBeInTheDocument();
  });

  it("shows a session-expiry message when adding an approval 401s (#5215)", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({});
    mockGetApprovals.mockResolvedValue({ approvals: [] });
    const unauthorized = new Error("HTTP 401 - Unauthorized (/accounts/alex/approvals)");
    (unauthorized as any).status = 401;
    mockAddApproval.mockRejectedValue(unauthorized);

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    const tickerInput = await screen.findByPlaceholderText("Ticker");
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement;
    await act(async () => {
      await userEvent.type(tickerInput, "ABC");
      fireEvent.change(dateInput, { target: { value: "2024-01-01" } });
    });
    const addButton = screen.getByRole("button", { name: /add/i });
    await act(async () => {
      await userEvent.click(addButton);
    });

    expect(await screen.findByText(/session has expired/i)).toBeInTheDocument();
  });

  it("shows a permission-specific message when removing an approval 403s (#5215)", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({});
    mockGetApprovals.mockResolvedValue({
      approvals: [{ ticker: "ABC", approved_on: "2024-01-01" }],
    });
    const forbidden = new Error("HTTP 403 - Forbidden (/accounts/alex/approvals)");
    (forbidden as any).status = 403;
    mockRemoveApproval.mockRejectedValue(forbidden);

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    const removeButton = await screen.findByRole("button", { name: /remove/i });
    await act(async () => {
      await userEvent.click(removeButton);
    });

    expect(
      await screen.findByText(/don't have permission to view or manage approvals/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Failed to remove approval$/)).not.toBeInTheDocument();
  });

  it("shows a session-expiry message when removing an approval 401s (#5215)", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({});
    mockGetApprovals.mockResolvedValue({
      approvals: [{ ticker: "ABC", approved_on: "2024-01-01" }],
    });
    const unauthorized = new Error("HTTP 401 - Unauthorized (/accounts/alex/approvals)");
    (unauthorized as any).status = 401;
    mockRemoveApproval.mockRejectedValue(unauthorized);

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    const removeButton = await screen.findByRole("button", { name: /remove/i });
    await act(async () => {
      await userEvent.click(removeButton);
    });

    expect(await screen.findByText(/session has expired/i)).toBeInTheDocument();
  });

  it("falls back to the generic message for a non-permission approvals failure", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({});
    const serverError = new Error("HTTP 500 - Internal Server Error (/accounts/alex/approvals)");
    (serverError as any).status = 500;
    mockGetApprovals.mockRejectedValue(serverError);

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    expect(await screen.findByText(/^Failed to load approvals$/)).toBeInTheDocument();
  });

  it("does not emit duplicate-key warnings when the same ticker is approved twice (#6505)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetUserConfig.mockResolvedValue({});
    mockGetApprovals.mockResolvedValue({
      approvals: [
        { ticker: "PFE", approved_on: "2026-01-01" },
        { ticker: "PFE", approved_on: "2026-01-01" },
      ],
    });

    render(<UserConfig />);

    const select = await screen.findByRole("combobox");
    await act(async () => {
      await userEvent.selectOptions(select, "alex");
    });

    // Scope to the approvals table so the assertion can't be satisfied by PFE
    // appearing anywhere else on the page.
    const approvalsTable = await screen.findByRole("table");
    expect(within(approvalsTable).getAllByText("PFE")).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });
});

