import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AllowanceGuardianCard from "@/components/AllowanceGuardianCard";
import { getAllowanceGuardian, type AllowanceGuardianReport } from "@/api";

vi.mock("@/api", () => ({ getAllowanceGuardian: vi.fn() }));
const mockGetGuardian = vi.mocked(getAllowanceGuardian);

const NOT_MODELLED = [
  "Tapered annual allowance: not modelled.",
  "Money purchase annual allowance (MPAA): not modelled.",
  "Pensions not recorded in AllotMint are not counted.",
];
const ADVISER_NOTE = "Information, not advice: take decisions with a regulated financial adviser.";

function report(overrides: Partial<AllowanceGuardianReport> = {}): AllowanceGuardianReport {
  return {
    owner: "alex",
    as_of: "2026-10-09",
    tax_year: "2026-2027",
    schedule_count: 1,
    contributions: {
      results: [
        {
          account: "sipp",
          source: "employer",
          label: "Salary sacrifice",
          expected_date: "2026-05-28",
          expected_amount_minor: 250_000,
          status: "late",
          received_amount_minor: 250_000,
          difference_minor: 0,
          days_late: 3,
        },
        {
          account: "sipp",
          source: "employer",
          label: "Salary sacrifice",
          expected_date: "2026-06-28",
          expected_amount_minor: 250_000,
          status: "missing",
          received_amount_minor: null,
          difference_minor: null,
          days_late: null,
        },
      ],
      counts: { on_time: 0, late: 1, wrong_amount: 0, missing: 1, awaiting: 0 },
    },
    pension_allowance: {
      available: true,
      tax_year: "2026-2027",
      annual_allowance_minor: 6_000_000,
      used_to_date_minor: 5_000_000,
      current_year_remaining_minor: 1_000_000,
      carry_forward_available_minor: 9_000_000,
      carry_forward_by_year: [],
      scheduled_remaining_minor: 15_000_000,
      projected_total_minor: 20_000_000,
      carry_forward_first_needed: { date: "2026-10-28", month: "2026-10" },
      projected_breach: { date: "2027-02-28", month: "2027-02" },
      projected_excess_minor: 5_000_000,
    },
    isa_allowance: { available: false, reason: "allotmint-pro not installed" },
    alerts: [
      { level: "critical", code: "pension_projected_breach", message: "Projected over in 2027-02." },
    ],
    not_modelled: NOT_MODELLED,
    assumptions: [],
    adviser_note: ADVISER_NOTE,
    ...overrides,
  };
}

const table = () => screen.getByRole("table");

describe("AllowanceGuardianCard", () => {
  it("shows the projection, statuses, alerts and guardrails", async () => {
    mockGetGuardian.mockResolvedValue(report());
    render(<AllowanceGuardianCard owner="alex" />);

    expect(await screen.findByText("Projected over in 2027-02.")).toBeInTheDocument();
    expect(mockGetGuardian).toHaveBeenCalledWith("alex");
    expect(screen.getByText("2027-02")).toBeInTheDocument();
    expect(screen.getByText("2026-10")).toBeInTheDocument();
    expect(screen.getByText("£100,000.00")).toBeInTheDocument(); // 10,000 + 90,000 available, from pence
    expect(within(table()).getAllByText("£2,500.00")).toHaveLength(3); // 250,000 pence

    expect(within(table()).getByText("Late")).toBeInTheDocument();
    expect(within(table()).getByText("Missing")).toBeInTheDocument();

    for (const item of NOT_MODELLED) expect(screen.getByText(item)).toBeInTheDocument();
    expect(screen.getByText(ADVISER_NOTE)).toBeInTheDocument();
    expect(screen.getByText(/not available in this deployment/i)).toBeInTheDocument();
  });

  it("still shows what is not modelled and the adviser note when loading fails", async () => {
    mockGetGuardian.mockRejectedValue(new Error("boom"));
    render(<AllowanceGuardianCard owner="alex" />);

    expect(await screen.findByText(/failed to load the allowance guardian/i)).toBeInTheDocument();
    expect(screen.getByText(/tapered annual allowance/i)).toBeInTheDocument();
    expect(screen.getByText(/regulated financial adviser/i)).toBeInTheDocument();
  });

  it("explains when no schedule has been recorded", async () => {
    mockGetGuardian.mockResolvedValue(
      report({ schedule_count: 0, contributions: { results: [], counts: report().contributions.counts } }),
    );
    render(<AllowanceGuardianCard owner="alex" />);
    expect(await screen.findByText(/no contribution schedule recorded/i)).toBeInTheDocument();
  });
});
