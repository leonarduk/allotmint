import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AddPositionForm } from "@/components/AddPositionForm";
import { createManualHolding } from "@/api";

vi.mock("@/api", () => ({
  createManualHolding: vi.fn(),
}));

describe("AddPositionForm", () => {
  beforeEach(() => {
    vi.mocked(createManualHolding).mockReset();
  });

  it("submits units + price for the selected account", async () => {
    vi.mocked(createManualHolding).mockResolvedValue({
      status: "saved",
      owner: "alice",
      account: "sipp",
      holding: { ticker: "VWRL.L" },
    });

    render(<AddPositionForm owner="alice" accounts={["ISA", "SIPP"]} />);

    await userEvent.selectOptions(screen.getByLabelText("Account"), "SIPP");
    await userEvent.type(screen.getByLabelText("Ticker"), "vwrl.l");
    await userEvent.type(screen.getByLabelText("Units"), "10");
    await userEvent.type(screen.getByLabelText("Price (GBP)"), "100");
    await userEvent.click(screen.getByRole("button", { name: "Add position" }));

    expect(createManualHolding).toHaveBeenCalledWith({
      owner: "alice",
      account: "SIPP",
      ticker: "VWRL.L",
      units: 10,
      price_gbp: 100,
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Position added.");
  });

  it("submits a direct GBP value when that mode is selected", async () => {
    vi.mocked(createManualHolding).mockResolvedValue({
      status: "saved",
      owner: "alice",
      account: "isa",
      holding: { ticker: "AAA.L" },
    });

    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    await userEvent.type(screen.getByLabelText("Ticker"), "AAA.L");
    await userEvent.selectOptions(screen.getByLabelText("Amount"), "Value (GBP)");
    await userEvent.type(screen.getByLabelText("Value (GBP)"), "500");
    await userEvent.click(screen.getByRole("button", { name: "Add position" }));

    expect(createManualHolding).toHaveBeenCalledWith({
      owner: "alice",
      account: "ISA",
      ticker: "AAA.L",
      value_gbp: 500,
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Position added.");
  });

  it("requires a ticker before submitting", async () => {
    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    await userEvent.type(screen.getByLabelText("Units"), "10");
    await userEvent.type(screen.getByLabelText("Price (GBP)"), "100");
    await userEvent.click(screen.getByRole("button", { name: "Add position" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Ticker is required.");
    expect(createManualHolding).not.toHaveBeenCalled();
  });

  it("requires both units and price when in units + price mode", async () => {
    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    await userEvent.type(screen.getByLabelText("Ticker"), "AAA.L");
    await userEvent.type(screen.getByLabelText("Units"), "10");
    await userEvent.click(screen.getByRole("button", { name: "Add position" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Provide either a value, or both units and price.",
    );
    expect(createManualHolding).not.toHaveBeenCalled();
  });

  it("surfaces backend errors", async () => {
    vi.mocked(createManualHolding).mockRejectedValue(
      new Error("HTTP 400 - Bad Request"),
    );

    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    await userEvent.type(screen.getByLabelText("Ticker"), "AAA.L");
    await userEvent.type(screen.getByLabelText("Units"), "10");
    await userEvent.type(screen.getByLabelText("Price (GBP)"), "100");
    await userEvent.click(screen.getByRole("button", { name: "Add position" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 400 - Bad Request");
  });
});
