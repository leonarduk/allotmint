import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AddPositionForm } from "@/components/AddPositionForm";
import { createManualHolding } from "@/api";
import { AuthContext } from "@/AuthContext";

vi.mock("@/api", () => ({
  createManualHolding: vi.fn(),
}));

const localToday = () => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

const previewResult = (overrides: Record<string, unknown> = {}) => ({
  status: "preview",
  owner: "alice",
  account: "sipp",
  holding: { ticker: "PHGP.L", units: 34, price: 288.89 },
  units_before: 21,
  transaction: {
    type: "TRANSFER_IN",
    ticker: "PHGP.L",
    date: "2026-10-07",
    units: 13,
    price_gbp: 288.89,
  },
  price_warning: null,
  ...overrides,
});

const savedResult = { status: "saved", owner: "alice", account: "sipp", holding: { ticker: "PHGP.L" } };

describe("AddPositionForm", () => {
  beforeEach(() => {
    vi.mocked(createManualHolding).mockReset();
  });

  it("explains that units are the total holding, not a single trade", () => {
    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    expect(screen.getByText(/Enter the TOTAL units you hold/)).toBeInTheDocument();
    expect(screen.getByLabelText("Date of change")).toHaveValue(localToday());
  });

  it("previews the computed transfer before saving units + price", async () => {
    vi.mocked(createManualHolding)
      .mockResolvedValueOnce(previewResult())
      .mockResolvedValueOnce(savedResult);

    render(<AddPositionForm owner="alice" accounts={["ISA", "SIPP"]} />);

    await userEvent.selectOptions(screen.getByLabelText("Account"), "SIPP");
    await userEvent.type(screen.getByLabelText("Ticker"), "phgp.l");
    await userEvent.type(screen.getByLabelText("Units"), "34");
    await userEvent.type(screen.getByLabelText("Price (GBP)"), "288.89");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    const expected = {
      owner: "alice",
      account: "SIPP",
      ticker: "PHGP.L",
      units: 34,
      price_gbp: 288.89,
      date: localToday(),
    };
    expect(createManualHolding).toHaveBeenCalledWith({ ...expected, dry_run: true });
    expect(await screen.findByTestId("add-position-preview")).toHaveTextContent(
      "This will record +13 units of PHGP.L as TRANSFER_IN dated 2026-10-07 at £288.89/unit (held now: 21, new total: 34).",
    );

    await userEvent.click(screen.getByRole("button", { name: "Add position" }));

    expect(createManualHolding).toHaveBeenLastCalledWith({ ...expected, confirm_price: false });
    expect(await screen.findByRole("status")).toHaveTextContent("Position added.");
  });

  it("omits the date for an opening balance", async () => {
    vi.mocked(createManualHolding).mockResolvedValueOnce(previewResult());

    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    await userEvent.type(screen.getByLabelText("Ticker"), "AAA.L");
    await userEvent.type(screen.getByLabelText("Units"), "10");
    await userEvent.type(screen.getByLabelText("Price (GBP)"), "100");
    await userEvent.click(screen.getByLabelText(/Opening balance/));
    expect(screen.getByLabelText("Date of change")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(createManualHolding).toHaveBeenCalledWith({
      owner: "alice",
      account: "ISA",
      ticker: "AAA.L",
      units: 10,
      price_gbp: 100,
      dry_run: true,
    });
  });

  it("warns about a likely pence/pounds mix-up and requires an explicit save", async () => {
    const message = "Price £28,889.40 for PHGP.L is 99.6x the latest known price £290.00; possibly pence entered as pounds";
    vi.mocked(createManualHolding)
      .mockResolvedValueOnce(
        previewResult({ price_warning: { latest_price_gbp: 290, ratio: 99.6, suggested_price_gbp: 288.89, message } }),
      )
      .mockResolvedValueOnce(savedResult);

    render(<AddPositionForm owner="alice" accounts={["SIPP"]} />);

    await userEvent.type(screen.getByLabelText("Ticker"), "PHGP.L");
    await userEvent.type(screen.getByLabelText("Units"), "34");
    await userEvent.type(screen.getByLabelText("Price (GBP)"), "28889.4");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(`Check the price: ${message}`);
    await userEvent.click(screen.getByRole("button", { name: "Save anyway" }));

    expect(createManualHolding).toHaveBeenLastCalledWith(expect.objectContaining({ confirm_price: true }));
  });

  it("discards the preview when an input changes", async () => {
    vi.mocked(createManualHolding).mockResolvedValue(previewResult());

    render(<AddPositionForm owner="alice" accounts={["SIPP"]} />);

    await userEvent.type(screen.getByLabelText("Ticker"), "PHGP.L");
    await userEvent.type(screen.getByLabelText("Units"), "34");
    await userEvent.type(screen.getByLabelText("Price (GBP)"), "288.89");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByTestId("add-position-preview")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Units"), "5");

    expect(screen.queryByTestId("add-position-preview")).toBeNull();
    expect(screen.getByRole("button", { name: "Preview" })).toBeInTheDocument();
  });

  it("previews a direct GBP value when that mode is selected", async () => {
    vi.mocked(createManualHolding).mockResolvedValueOnce(previewResult());

    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    await userEvent.type(screen.getByLabelText("Ticker"), "AAA.L");
    await userEvent.selectOptions(screen.getByLabelText("Amount"), "Value (GBP)");
    await userEvent.type(screen.getByLabelText("Value (GBP)"), "500");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(createManualHolding).toHaveBeenCalledWith({
      owner: "alice",
      account: "ISA",
      ticker: "AAA.L",
      value_gbp: 500,
      date: localToday(),
      dry_run: true,
    });
  });

  it("requires a ticker before submitting", async () => {
    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    await userEvent.type(screen.getByLabelText("Units"), "10");
    await userEvent.type(screen.getByLabelText("Price (GBP)"), "100");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Ticker is required.");
    expect(createManualHolding).not.toHaveBeenCalled();
  });

  it("requires both units and price when in units + price mode", async () => {
    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    await userEvent.type(screen.getByLabelText("Ticker"), "AAA.L");
    await userEvent.type(screen.getByLabelText("Units"), "10");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

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
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 400 - Bad Request");
  });

  it("does not render a collapse button when onCollapse is not provided", () => {
    render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

    expect(screen.queryByRole("button", { name: "Collapse add position form" })).toBeNull();
  });

  it("renders duplicate account types without a React key warning", () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    render(
      <AddPositionForm owner="alice" accounts={["ISA", "ISA", "SIPP"]} />,
    );

    expect(
      screen.getByLabelText("Account").querySelectorAll("option"),
    ).toHaveLength(3);
    expect(consoleError.mock.calls.flat().join(" ")).not.toContain("same key");
    consoleError.mockRestore();
  });

  it("calls onCollapse when the collapse button is clicked", async () => {
    const onCollapse = vi.fn();
    render(<AddPositionForm owner="alice" accounts={["ISA"]} onCollapse={onCollapse} />);

    await userEvent.click(screen.getByRole("button", { name: "Collapse add position form" }));

    expect(onCollapse).toHaveBeenCalledTimes(1);
  });

  it("labels the collapse control and exposes its expanded state", () => {
    render(
      <AddPositionForm
        owner="alice"
        accounts={["ISA"]}
        onCollapse={vi.fn()}
        controlsId="add-position-form"
      />,
    );

    const button = screen.getByRole("button", { name: "Collapse add position form" });
    expect(button).toHaveTextContent("Collapse");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveAttribute("aria-controls", "add-position-form");
    expect(screen.getByRole("form", { name: "Add position" })).toHaveAttribute(
      "id",
      "add-position-form",
    );
  });

  // Issue #7411: mutating controls must disable themselves for a
  // demo-scoped session so a visitor isn't shown a button that will 403.
  describe("demoReadOnly (issue #7411)", () => {
    it("disables the submit button with an explanatory title", () => {
      render(
        <AuthContext.Provider
          value={{
            user: null,
            setUser: vi.fn(),
            logout: null,
            setLogout: vi.fn(),
            demoReadOnly: true,
            setDemoReadOnly: vi.fn(),
          }}
        >
          <AddPositionForm owner="alice" accounts={["ISA"]} />
        </AuthContext.Provider>,
      );

      const submit = screen.getByRole("button", { name: "Preview" });
      expect(submit).toBeDisabled();
      expect(submit).toHaveAttribute("title");
    });

    it("does not block submission when demoReadOnly is false (default)", async () => {
      vi.mocked(createManualHolding).mockResolvedValue({
        status: "saved",
        owner: "alice",
        account: "isa",
        holding: { ticker: "AAA.L" },
      });

      render(<AddPositionForm owner="alice" accounts={["ISA"]} />);

      const submit = screen.getByRole("button", { name: "Preview" });
      expect(submit).not.toBeDisabled();

      await userEvent.type(screen.getByLabelText("Ticker"), "AAA.L");
      await userEvent.type(screen.getByLabelText("Units"), "10");
      await userEvent.type(screen.getByLabelText("Price (GBP)"), "100");
      await userEvent.click(submit);

      expect(createManualHolding).toHaveBeenCalled();
    });
  });
});
