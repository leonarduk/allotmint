import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import VirtualPortfolio from "@/pages/VirtualPortfolio";

const STORAGE_KEY = "familyManualPortfolio.v1";

describe("VirtualPortfolio page", () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
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

    const accountNameInput = screen.getByLabelText("Account name");
    fireEvent.change(accountNameInput, { target: { value: "Brokerage Main" } });

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
    expect(screen.queryByPlaceholderText("AAPL")).not.toBeInTheDocument();
  });

  it("shows a status message when localStorage write fails", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });

    render(<VirtualPortfolio />);

    const addInput = screen.getByPlaceholderText(/Account name/i);
    fireEvent.change(addInput, { target: { value: "ISA" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));

    expect(screen.getByText("Could not save your changes in this browser.")).toBeInTheDocument();
  });
});
