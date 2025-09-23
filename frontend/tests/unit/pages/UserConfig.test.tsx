import { render, screen, act } from "@testing-library/react";
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
});

