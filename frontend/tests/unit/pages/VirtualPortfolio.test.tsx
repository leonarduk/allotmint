import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import VirtualPortfolio from "@/pages/VirtualPortfolio";
import * as api from "@/api";

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    logAnalyticsEvent: vi.fn().mockResolvedValue(undefined),
  };
});

const STORAGE_KEY = "familyManualPortfolio.v1";

describe("VirtualPortfolio page", () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("sends a view analytics event", () => {
    const mockLogAnalyticsEvent = vi.mocked(api.logAnalyticsEvent);
    render(<VirtualPortfolio />);
    expect(mockLogAnalyticsEvent).toHaveBeenCalledWith(
      expect.objectContaining({ source: "virtual_portfolio", event: "view" }),
    );
  });

  it("adds multiple accounts and holdings", () => {
    render(<VirtualPortfolio />);

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: "ISA" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));

    fireEvent.change(addInput, { target: { value: "Pension" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));

    expect(screen.getAllByLabelText("Account name")).toHaveLength(2);

    fireEvent.click(screen.getAllByRole("button", { name: "Add holding" })[0]);

    const tickerInputs = screen.getAllByPlaceholderText("AAPL");
    expect(tickerInputs.length).toBeGreaterThanOrEqual(3);
  });

  it("persists and hydrates from localStorage", () => {
    render(<VirtualPortfolio />);

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: "Brokerage" } });
    fireEvent.submit(addInput.closest("form")!);

    // Rename via the account name input: change + blur to commit.
    const accountNameInput = screen.getByLabelText("Account name");
    fireEvent.change(accountNameInput, { target: { value: "Brokerage Main" } });
    fireEvent.blur(accountNameInput);

    const stored = window.localStorage.getItem(STORAGE_KEY);
    expect(stored).toContain("Brokerage Main");

    render(<VirtualPortfolio />);
    expect(screen.getAllByDisplayValue("Brokerage Main").length).toBeGreaterThan(0);
  });

  it("prevents duplicate account names and shows feedback", () => {
    render(<VirtualPortfolio />);

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: "ISA" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));

    fireEvent.change(addInput, { target: { value: "isa" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));

    expect(screen.getByText("Use a unique account name.")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Account name")).toHaveLength(1);
  });

  it("filters malformed holdings from stored payload", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        {
          id: "a-1",
          name: "ISA",
          holdings: [{ ticker: "AAPL" }],
        },
      ]),
    );

    render(<VirtualPortfolio />);

    expect(screen.getByLabelText("Account name")).toHaveValue("ISA");
    // Malformed holding was stripped; account still gets one blank holding row.
    expect(screen.getByPlaceholderText("AAPL")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("AAPL")).toHaveValue("");
  });

  it("shows a status message when localStorage write fails", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });

    render(<VirtualPortfolio />);

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: "ISA" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));

    expect(
      screen.getByText("Changes were not saved in this browser. Try freeing local storage space."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Account name")).not.toBeInTheDocument();
  });

  it("allows typing an intermediate empty value without snapping back", () => {
    render(<VirtualPortfolio />);

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: "ISA" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));

    const accountNameInput = screen.getByLabelText("Account name");

    // Clear the field mid-edit — input should show empty, not snap back to "ISA".
    fireEvent.change(accountNameInput, { target: { value: "" } });
    expect(accountNameInput).toHaveValue("");

    // Blur without a valid value — input reverts to saved name, warning shown.
    fireEvent.blur(accountNameInput);
    expect(screen.getByText("Account name cannot be empty.")).toBeInTheDocument();
    expect(accountNameInput).toHaveValue("ISA");
  });

  it("rejects duplicate account renames on blur", () => {
    render(<VirtualPortfolio />);

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: "ISA" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));
    fireEvent.change(addInput, { target: { value: "Pension" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));

    // Try to rename Pension to ISA (case-insensitive).
    const [, pensionInput] = screen.getAllByLabelText("Account name");
    fireEvent.change(pensionInput, { target: { value: "isa" } });
    fireEvent.blur(pensionInput);

    expect(screen.getByText("Account names must stay unique.")).toBeInTheDocument();
    // Input should revert to "Pension", not remain as "isa".
    expect(pensionInput).toHaveValue("Pension");
  });

  it("disables the Remove button when only one holding remains", () => {
    render(<VirtualPortfolio />);

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: "ISA" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));

    // Single holding row — Remove button must be disabled.
    const removeButton = screen.getByRole("button", { name: "Remove holding" });
    expect(removeButton).toBeDisabled();

    // Add a second holding — Remove should now be enabled.
    fireEvent.click(screen.getByRole("button", { name: "Add holding" }));
    const removeButtons = screen.getAllByRole("button", { name: "Remove holding" });
    expect(removeButtons).toHaveLength(2);
    removeButtons.forEach((btn) => expect(btn).not.toBeDisabled());
  });
});
