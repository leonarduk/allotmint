import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InstrumentSleevePicker } from "@/components/InstrumentSleevePicker";
import { assignSleeve, getSleeves } from "@/api";
import type { InstrumentPosition, Sleeve, SleeveHolding, SleeveList } from "@/types";

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return { ...actual, getSleeves: vi.fn(), assignSleeve: vi.fn() };
});
const mockGetSleeves = vi.mocked(getSleeves);
const mockAssign = vi.mocked(assignSleeve);

const sleeve = (id: string, name: string): Sleeve => ({ id, name, size_pct: 10, targets: {}, strategy: null });
const CORE = sleeve("core", "Core");
const SPEC = sleeve("sleeve-spec", "Speculative");
const held = (ticker: string): SleeveHolding => ({ ticker, name: null, sector: null, value: 1, sleeve_id: "core" });
const listing = (sleeves: Sleeve[], tickers: string[], assignments: Record<string, string> = {}): SleeveList => ({
  sleeves,
  assignments,
  holdings: tickers.map(held),
});
const position = (owner: string, account = "isa"): InstrumentPosition => ({ owner, account, units: 1 });

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("InstrumentSleevePicker", () => {
  it("renders nothing and loads no sleeves when nobody holds the instrument", () => {
    const { container } = render(<InstrumentSleevePicker ticker="AAA.L" positions={[]} />);
    expect(container).toBeEmptyDOMElement();
    expect(mockGetSleeves).not.toHaveBeenCalled();
  });

  it("hides the picker for an owner with only the core sleeve", async () => {
    mockGetSleeves.mockResolvedValue(listing([CORE], ["AAA.L"]));
    render(<InstrumentSleevePicker ticker="AAA.L" positions={[position("alice")]} />);
    await waitFor(() => expect(mockGetSleeves).toHaveBeenCalledWith("alice"));
    await act(async () => {});
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("hides the picker when the owner's holdings listing does not include the ticker", async () => {
    mockGetSleeves.mockResolvedValue(listing([CORE, SPEC], ["BBB.L"]));
    render(<InstrumentSleevePicker ticker="AAA.L" positions={[position("alice")]} />);
    await waitFor(() => expect(mockGetSleeves).toHaveBeenCalledWith("alice"));
    await act(async () => {});
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("moves the holding into a sleeve through the owner's route", async () => {
    mockGetSleeves.mockResolvedValue(listing([CORE, SPEC], ["AAA.L"]));
    mockAssign.mockResolvedValue(listing([CORE, SPEC], ["AAA.L"], { "AAA.L": "sleeve-spec" }));
    const user = userEvent.setup();
    // Two accounts for one owner still give one picker.
    render(<InstrumentSleevePicker ticker="aaa.l" positions={[position("alice"), position("alice", "sipp")]} />);

    // The lower-cased route ticker is matched and sent in the backend's upper-cased form.
    const select = await screen.findByRole("combobox", { name: "Sleeve for AAA.L (alice)" });
    expect(select).toHaveValue("core");
    expect(mockGetSleeves).toHaveBeenCalledTimes(1);

    await user.selectOptions(select, "sleeve-spec");
    expect(mockAssign).toHaveBeenCalledWith("alice", "AAA.L", "sleeve-spec");
    await waitFor(() => expect(select).toHaveValue("sleeve-spec"));
  });

  it("gives each owner their own picker, writing only that owner's tag", async () => {
    mockGetSleeves.mockImplementation((owner: string) =>
      Promise.resolve(
        owner === "alice"
          ? listing([CORE, SPEC], ["AAA.L"], { "AAA.L": "sleeve-spec" })
          : owner === "bob"
            ? listing([CORE, sleeve("sleeve-bob", "Punts")], ["AAA.L"])
            : listing([CORE], ["AAA.L"]),
      ),
    );
    mockAssign.mockResolvedValue(listing([CORE, sleeve("sleeve-bob", "Punts")], ["AAA.L"]));
    const user = userEvent.setup();
    render(
      <InstrumentSleevePicker ticker="AAA.L" positions={[position("bob"), position("carol"), position("alice")]} />,
    );

    const alice = await screen.findByRole("combobox", { name: "Sleeve for AAA.L (alice)" });
    const bob = await screen.findByRole("combobox", { name: "Sleeve for AAA.L (bob)" });
    expect(alice).toHaveValue("sleeve-spec");
    expect(bob).toHaveValue("core");
    // carol has only the core sleeve.
    expect(screen.queryByRole("combobox", { name: /carol/ })).not.toBeInTheDocument();

    // The visible label is the only name source, and each picker has its own (#11173).
    for (const select of [alice, bob]) {
      expect(select).not.toHaveAttribute("aria-label");
      const labelId = select.getAttribute("aria-labelledby");
      expect(labelId).toBeTruthy();
      expect(document.querySelectorAll(`[id="${labelId}"]`)).toHaveLength(1);
    }
    expect(alice.getAttribute("aria-labelledby")).not.toBe(bob.getAttribute("aria-labelledby"));

    await user.selectOptions(bob, "sleeve-bob");
    expect(mockAssign).toHaveBeenCalledTimes(1);
    expect(mockAssign).toHaveBeenCalledWith("bob", "AAA.L", "sleeve-bob");
    expect(alice).toHaveValue("sleeve-spec");
  });

  it("hides the picker when the listing has no holdings field (intended)", async () => {
    mockGetSleeves.mockResolvedValue({ sleeves: [CORE, SPEC], assignments: {} } as unknown as SleeveList);
    render(<InstrumentSleevePicker ticker="AAA.L" positions={[position("alice")]} />);
    await waitFor(() => expect(mockGetSleeves).toHaveBeenCalledWith("alice"));
    await act(async () => {});
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("shows the backend's error when the assignment is rejected", async () => {
    mockGetSleeves.mockResolvedValue(listing([CORE, SPEC], ["AAA.L"]));
    mockAssign.mockRejectedValue(new Error("'AAA.L' is not one of this owner's holdings"));
    const user = userEvent.setup();
    render(<InstrumentSleevePicker ticker="AAA.L" positions={[position("alice")]} />);

    await user.selectOptions(await screen.findByRole("combobox"), "sleeve-spec");
    expect(await screen.findByRole("alert")).toHaveTextContent("not one of this owner's holdings");
  });
});
