import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import "@/i18n";
import PriceTriggersPanel from "@/components/PriceTriggersPanel";
import type { PriceTrigger } from "@/api";

const mockList = vi.hoisted(() => vi.fn());
const mockCreate = vi.hoisted(() => vi.fn());
const mockUpdate = vi.hoisted(() => vi.fn());
const mockDelete = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  getPriceTriggers: mockList,
  createPriceTrigger: mockCreate,
  updatePriceTrigger: mockUpdate,
  deletePriceTrigger: mockDelete,
}));

const row: PriceTrigger = {
  id: "abc",
  ticker: "VOD.L",
  condition: "above",
  price: 1.5,
  mode: "once",
  enabled: true,
  note: "trim",
  created_at: "2026-01-01T00:00:00Z",
  last_triggered_at: null,
  last_triggered_price: null,
  trigger_count: 0,
};

beforeEach(() => {
  mockList.mockReset().mockResolvedValue([row]);
  mockCreate.mockReset().mockResolvedValue(row);
  mockUpdate.mockReset().mockResolvedValue(row);
  mockDelete.mockReset().mockResolvedValue({ status: "deleted" });
});

describe("PriceTriggersPanel", () => {
  it("lists existing triggers for the identity", async () => {
    render(<PriceTriggersPanel identity="demo" disabled={false} />);
    expect(await screen.findByText("VOD.L")).toBeInTheDocument();
    expect(mockList).toHaveBeenCalledWith("demo");
    expect(screen.getByText(/£1\.50/)).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    mockList.mockResolvedValue([]);
    render(<PriceTriggersPanel identity="demo" disabled={false} />);
    expect(await screen.findByText("No price triggers yet.")).toBeInTheDocument();
  });

  it("creates a continuous trigger from the form", async () => {
    mockList.mockResolvedValue([]);
    render(<PriceTriggersPanel identity="demo" disabled={false} />);
    await screen.findByText("No price triggers yet.");
    const add = screen.getByRole("button", { name: "Add trigger" });
    expect(add).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: " azn.l " } });
    fireEvent.change(screen.getByLabelText("Condition"), { target: { value: "below" } });
    fireEvent.change(screen.getByLabelText("Price (£)"), { target: { value: "90.5" } });
    fireEvent.change(screen.getByLabelText("Fires"), { target: { value: "continuous" } });
    fireEvent.click(add);

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith("demo", {
        ticker: "azn.l",
        condition: "below",
        price: 90.5,
        mode: "continuous",
        note: null,
      }),
    );
  });

  it("edits a trigger via the form", async () => {
    render(<PriceTriggersPanel identity="demo" disabled={false} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Ticker")).toHaveValue("VOD.L");
    fireEvent.change(screen.getByLabelText("Price (£)"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Update trigger" }));
    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(
        "demo",
        "abc",
        expect.objectContaining({ price: 2, ticker: "VOD.L", note: "trim" }),
      ),
    );
  });

  it("toggles enabled and deletes", async () => {
    render(<PriceTriggersPanel identity="demo" disabled={false} />);
    fireEvent.click(await screen.findByLabelText("Enabled VOD.L"));
    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith("demo", "abc", { enabled: false }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("demo", "abc"));
  });

  it("surfaces backend errors", async () => {
    mockCreate.mockRejectedValue(new Error("limit of 100 price triggers per user reached"));
    mockList.mockResolvedValue([]);
    render(<PriceTriggersPanel identity="demo" disabled={false} />);
    await screen.findByText("No price triggers yet.");
    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Price (£)"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add trigger" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("limit of 100");
  });

  it("scopes the list and new triggers to one ticker", async () => {
    mockList.mockResolvedValue([row, { ...row, id: "def", ticker: "AZN.L", price: 99 }]);
    render(
      <PriceTriggersPanel identity="demo" disabled={false} ticker="AZN.L" latestPrice={101.234} />,
    );
    expect(await screen.findByText(/£99\.00/)).toBeInTheDocument();
    expect(screen.queryByText(/£1\.50/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Ticker")).not.toBeInTheDocument();
    expect(screen.getByText("Latest price: £101.23")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Price (£)"), { target: { value: "110" } });
    fireEvent.click(screen.getByRole("button", { name: "Add trigger" }));
    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith("demo", expect.objectContaining({ ticker: "AZN.L", price: 110 })),
    );
  });

  it("shows a ticker-specific empty state when scoped", async () => {
    render(<PriceTriggersPanel identity="demo" disabled={false} ticker="AZN.L" />);
    expect(await screen.findByText("No price alerts for AZN.L yet.")).toBeInTheDocument();
  });

  it("disables editing controls when read-only", async () => {
    render(<PriceTriggersPanel identity="demo" disabled />);
    await screen.findByText("VOD.L");
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.getByLabelText("Ticker")).toBeDisabled();
  });
});
