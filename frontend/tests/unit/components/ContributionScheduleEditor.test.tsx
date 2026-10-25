import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ContributionScheduleEditor from "@/components/ContributionScheduleEditor";
import { minorToPounds, poundsToMinor } from "@/lib/minorUnits";
import { getContributionSchedule, getOwners, putContributionSchedule, type ContributionSchedule } from "@/api";
import { AuthContext } from "@/AuthContext";

vi.mock("@/api", () => ({
  getContributionSchedule: vi.fn(),
  getOwners: vi.fn(),
  putContributionSchedule: vi.fn(),
}));
const mockGet = vi.mocked(getContributionSchedule);
const mockPut = vi.mocked(putContributionSchedule);
const mockOwners = vi.mocked(getOwners);

const SCHEDULE: ContributionSchedule = {
  owner: "alex",
  contributions: [
    {
      account: "sipp",
      amount_minor: 250_000,
      frequency: "monthly",
      source: "employer",
      expected_day: 28,
      start_date: "2026-04-28",
      end_date: null,
      label: "Salary sacrifice",
    },
  ],
};

const row = (n: number) => screen.getByRole("group", { name: `Contribution ${n}` });

beforeEach(() => {
  vi.clearAllMocks();
  mockOwners.mockResolvedValue([{ owner: "alex", accounts: ["sipp", "isa"] }]);
  mockPut.mockImplementation(async (_owner, schedule) => schedule);
});

describe("poundsToMinor", () => {
  it("converts pounds to integer pence without float drift", () => {
    expect(poundsToMinor("0.1")).toBe(10);
    expect(poundsToMinor("0.2")).toBe(20);
    expect(poundsToMinor("0.30")).toBe(30);
    expect(poundsToMinor("£1,234.56")).toBe(123_456);
    expect(poundsToMinor("19.99")).toBe(1999);
  });

  it("rejects zero, negatives, extra decimals and junk", () => {
    for (const bad of ["", "0", "-5", "1.234", "abc", "1.2.3"]) expect(poundsToMinor(bad)).toBeNull();
  });

  it("formats pence back to pounds", () => {
    expect(minorToPounds(30)).toBe("0.30");
    expect(minorToPounds(250_000)).toBe("2500.00");
  });
});

describe("ContributionScheduleEditor", () => {
  it("loads the saved schedule with amounts shown in pounds", async () => {
    mockGet.mockResolvedValue(SCHEDULE);
    render(<ContributionScheduleEditor owner="alex" />);

    expect(await screen.findByDisplayValue("2500.00")).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("alex");
    expect(within(row(1)).getByLabelText("Source")).toHaveValue("employer");
    expect(within(row(1)).getByText(/counts at face value/i)).toBeInTheDocument();
  });

  it("saves edited and added rows as integer pence, then calls onSaved", async () => {
    mockGet.mockResolvedValue(SCHEDULE);
    const onSaved = vi.fn();
    const user = userEvent.setup();
    render(<ContributionScheduleEditor owner="alex" onSaved={onSaved} />);

    const amount = await screen.findByDisplayValue("2500.00");
    await user.clear(amount);
    await user.type(amount, "0.1");
    await user.click(screen.getByRole("button", { name: "Add contribution" }));
    await user.selectOptions(within(row(2)).getByLabelText("Account"), "isa");
    await user.type(within(row(2)).getByLabelText("Amount (£)"), "0.2");
    await user.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() => expect(mockPut).toHaveBeenCalledTimes(1));
    const [owner, payload] = mockPut.mock.calls[0];
    expect(owner).toBe("alex");
    expect(payload.owner).toBe("alex");
    expect(payload.contributions.map((c) => c.amount_minor)).toEqual([10, 20]);
    expect(payload.contributions[0]).toMatchObject({ account: "sipp", source: "employer", expected_day: 28 });
    // Choosing an ISA account switches the source to the only one ISA accounts take.
    expect(payload.contributions[1]).toMatchObject({ account: "isa", source: "isa_subscription" });
    expect(await screen.findByText("Schedule saved.")).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it("removes a row before saving", async () => {
    mockGet.mockResolvedValue(SCHEDULE);
    const user = userEvent.setup();
    render(<ContributionScheduleEditor owner="alex" />);

    await user.click(await screen.findByRole("button", { name: "Remove contribution 1" }));
    expect(screen.getByText(/No contributions recorded yet/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() => expect(mockPut).toHaveBeenCalledWith("alex", { owner: "alex", contributions: [] }));
  });

  it("blocks an invalid £ amount without calling the API", async () => {
    mockGet.mockResolvedValue(SCHEDULE);
    const user = userEvent.setup();
    render(<ContributionScheduleEditor owner="alex" />);

    const amount = await screen.findByDisplayValue("2500.00");
    await user.clear(amount);
    await user.type(amount, "12.345");
    await user.click(screen.getByRole("button", { name: "Save schedule" }));

    expect(screen.getByText(/positive amount in pounds/i)).toBeInTheDocument();
    expect(amount).toHaveAttribute("aria-invalid", "true");
    expect(mockPut).not.toHaveBeenCalled();
  });

  it("shows the backend's 400 validation detail and does not call onSaved", async () => {
    mockGet.mockResolvedValue(SCHEDULE);
    const detail =
      "contributions.0: isa_subscription is for ISA accounts only, and ISA accounts take only that source";
    mockPut.mockRejectedValue(Object.assign(new Error(detail), { status: 400 }));
    const onSaved = vi.fn();
    const user = userEvent.setup();
    render(<ContributionScheduleEditor owner="alex" onSaved={onSaved} />);

    await screen.findByDisplayValue("2500.00");
    await user.click(screen.getByRole("button", { name: "Save schedule" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(`Not saved: ${detail}`);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("shows a load error when the schedule cannot be fetched", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    render(<ContributionScheduleEditor owner="alex" />);
    expect(await screen.findByText("Failed to load the contribution schedule")).toBeInTheDocument();
  });

  it("is read-only in the demo", async () => {
    mockGet.mockResolvedValue(SCHEDULE);
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
        <ContributionScheduleEditor owner="alex" />
      </AuthContext.Provider>,
    );

    expect(await screen.findByDisplayValue("2500.00")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save schedule" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add contribution" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove contribution 1" })).toBeDisabled();
  });
});
