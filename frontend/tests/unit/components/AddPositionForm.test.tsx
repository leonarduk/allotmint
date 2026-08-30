import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AddPositionForm } from "@/components/AddPositionForm";
import { createManualHolding } from "@/api";
import { AuthContext } from "@/AuthContext";

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

      const submit = screen.getByRole("button", { name: "Add position" });
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

      const submit = screen.getByRole("button", { name: "Add position" });
      expect(submit).not.toBeDisabled();

      await userEvent.type(screen.getByLabelText("Ticker"), "AAA.L");
      await userEvent.type(screen.getByLabelText("Units"), "10");
      await userEvent.type(screen.getByLabelText("Price (GBP)"), "100");
      await userEvent.click(submit);

      expect(createManualHolding).toHaveBeenCalled();
    });
  });
});
