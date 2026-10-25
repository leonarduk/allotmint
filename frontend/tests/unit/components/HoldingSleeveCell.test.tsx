import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HoldingsTable } from "@/components/HoldingsTable";
import type { SleeveControl } from "@/components/HoldingSleeveCell";
import { useOwnerSleeveControl } from "@/hooks/useOwnerSleeveControl";
import { assignSleeve, getSleeves } from "@/api";
import { AuthContext } from "@/AuthContext";
import type { Holding, Sleeve, SleeveList } from "@/types";

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    getSleeves: vi.fn(),
    assignSleeve: vi.fn(),
    getInstrumentDetail: vi.fn(() => Promise.resolve({ mini: { 7: [], 30: [], 180: [] } })),
  };
});
const mockGetSleeves = vi.mocked(getSleeves);
const mockAssign = vi.mocked(assignSleeve);

const sleeve = (id: string, name: string): Sleeve => ({ id, name, size_pct: 10, targets: {}, strategy: null });
const CORE = sleeve("core", "Core");
const SPEC = sleeve("sleeve-spec", "Speculative");
const listing = (sleeves: Sleeve[], assignments: Record<string, string> = {}): SleeveList => ({
  sleeves,
  assignments,
  holdings: [],
});

const holdings: Holding[] = [
  { ticker: "aaa", name: "Alpha", units: 1, market_value_gbp: 10, cost_basis_gbp: 5, gain_gbp: 5 },
  { ticker: "BBB", name: "Beta", units: 1, market_value_gbp: 20, cost_basis_gbp: 10, gain_gbp: 10 },
];

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("useOwnerSleeveControl", () => {
  it("offers no control in a group view (no owner) and never loads sleeves", () => {
    const { result } = renderHook(() => useOwnerSleeveControl(null));
    expect(result.current).toBeUndefined();
    expect(mockGetSleeves).not.toHaveBeenCalled();
  });

  it("offers no control when the owner has only the core sleeve", async () => {
    mockGetSleeves.mockResolvedValue(listing([CORE]));
    const { result } = renderHook(() => useOwnerSleeveControl("alice"));
    await waitFor(() => expect(mockGetSleeves).toHaveBeenCalledWith("alice"));
    await act(async () => {});
    expect(result.current).toBeUndefined();
  });

  it("assigns through the owner's route, sending null for the core, and uses the returned listing", async () => {
    mockGetSleeves.mockResolvedValue(listing([CORE, SPEC]));
    mockAssign.mockResolvedValue(listing([CORE, SPEC], { AAA: "sleeve-spec" }));
    const { result } = renderHook(() => useOwnerSleeveControl("alice"));
    await waitFor(() => expect(result.current).toBeDefined());

    await act(() => result.current!.onAssign("aaa", "sleeve-spec"));
    expect(mockAssign).toHaveBeenCalledWith("alice", "aaa", "sleeve-spec");
    expect(result.current!.assignments).toEqual({ AAA: "sleeve-spec" });

    await act(() => result.current!.onAssign("aaa", "core"));
    expect(mockAssign).toHaveBeenLastCalledWith("alice", "aaa", null);
  });
});

describe("HoldingsTable sleeve column", () => {
  const control = (onAssign = vi.fn(() => Promise.resolve())): SleeveControl => ({
    sleeves: [CORE, SPEC],
    assignments: { AAA: "sleeve-spec", BBB: "sleeve-gone" },
    onAssign,
  });

  it("is absent without a sleeve control", () => {
    render(<HoldingsTable holdings={holdings} />);
    expect(screen.queryByRole("combobox", { name: "Sleeve for aaa" })).not.toBeInTheDocument();
  });

  it("is absent for rollup rows", () => {
    render(<HoldingsTable holdings={holdings} rollupMode sleeveControl={control()} />);
    expect(screen.queryByRole("combobox", { name: "Sleeve for aaa" })).not.toBeInTheDocument();
  });

  it("shows each holding's sleeve (upper-cased lookup, dangling tags in the core) and assigns on change", async () => {
    const onAssign = vi.fn(() => Promise.resolve());
    const onSelectInstrument = vi.fn();
    const user = userEvent.setup();
    render(<HoldingsTable holdings={holdings} sleeveControl={control(onAssign)} onSelectInstrument={onSelectInstrument} />);

    const aaa = screen.getByRole("combobox", { name: "Sleeve for aaa" });
    expect(aaa).toHaveValue("sleeve-spec");
    expect(within(aaa).getByRole("option", { name: "Core" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sleeve for BBB" })).toHaveValue("core");

    await user.selectOptions(aaa, "core");
    expect(onAssign).toHaveBeenCalledWith("aaa", "core");
    expect(onSelectInstrument).not.toHaveBeenCalled();
  });

  it("shows the backend's error when an assignment is rejected", async () => {
    const onAssign = vi.fn(() => Promise.reject(new Error("'BBB' is not one of this owner's holdings")));
    const user = userEvent.setup();
    render(<HoldingsTable holdings={holdings} sleeveControl={control(onAssign)} />);

    await user.selectOptions(screen.getByRole("combobox", { name: "Sleeve for BBB" }), "sleeve-spec");
    expect(await screen.findByRole("alert")).toHaveTextContent("not one of this owner's holdings");
  });

  it("is disabled in the read-only demo", () => {
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
        <HoldingsTable holdings={holdings} sleeveControl={control()} />
      </AuthContext.Provider>,
    );
    expect(screen.getByRole("combobox", { name: "Sleeve for aaa" })).toBeDisabled();
  });
});
