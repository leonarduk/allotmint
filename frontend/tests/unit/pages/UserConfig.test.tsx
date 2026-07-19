import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach, vi } from "vitest";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetUserConfig = vi.hoisted(() => vi.fn());
const mockGetApprovals = vi.hoisted(() => vi.fn());
const mockUpdateUserConfig = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  API_BASE: "",
  getOwners: mockGetOwners,
  getUserConfig: mockGetUserConfig,
  getApprovals: mockGetApprovals,
  updateUserConfig: mockUpdateUserConfig,
  addApproval: vi.fn(),
  removeApproval: vi.fn(),
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
});

