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
});

