import "@/setupTests";
import { render, screen, within, fireEvent, cleanup } from "@testing-library/react";
import type { ReactElement } from "react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import en from "@/locales/en/translation.json";

import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";

type RouteStateMock = {
  mode: "owner";
  setMode: ReturnType<typeof vi.fn>;
  selectedOwner: string;
  setSelectedOwner: ReturnType<typeof vi.fn>;
  selectedGroup: string;
  setSelectedGroup: ReturnType<typeof vi.fn>;
};

let routeState: RouteStateMock;

const mockUseRoute = vi.hoisted(() => vi.fn(() => routeState));

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetPensionForecast = vi.hoisted(() => vi.fn());
const mockGetPortfolio = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    getOwners: mockGetOwners,
    getPensionForecast: mockGetPensionForecast,
    getPortfolio: mockGetPortfolio,
  };
});

vi.mock("@/RouteContext", () => ({
  useRoute: mockUseRoute,
}));

function renderWithI18n(ui: ReactElement) {
  const i18n = createInstance();
  i18n.use(initReactI18next).init({
    lng: "en",
    resources: { en: { translation: en } },
  });
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe("PensionForecast page", () => {
  beforeEach(() => {
    routeState = {
      mode: "owner",
      setMode: vi.fn(),
      selectedOwner: "",
      setSelectedOwner: vi.fn(),
      selectedGroup: "",
      setSelectedGroup: vi.fn(),
    };
    mockUseRoute.mockImplementation(() => routeState);
    // Default: no portfolio accounts, so the pension-pot seeding effect
    // (#7211) resolves harmlessly for tests that don't care about it.
    mockGetPortfolio.mockResolvedValue({
      owner: "",
      as_of: "",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders owner selector", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
    expect(ownerSelect).toBeInTheDocument();
    const selects = await screen.findAllByLabelText(/owner/i, {
      selector: 'select',
    });
    expect(selects[0]).toBeInTheDocument();
  });

  it("rounds a fractional current age to a whole number", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 42.3716632443,
      retirement_age: 67,
      dob: "1984-01-15",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const btn = await screen.findByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await screen.findByText(/birth date: 1984-01-15/i);
    expect(screen.getByText("Current age: 42")).toBeInTheDocument();
    expect(
      screen.queryByText(/42\.3716632443/),
    ).not.toBeInTheDocument();
  });

  it("submits with selected owner", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
      { owner: "beth", full_name: "Beth Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 200,
      pension_pot_gbp: 123,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
      earliest_retirement_age: 64,
      retirement_income_breakdown: {
        state_pension_annual: 9000,
        defined_benefit_annual: 4000,
        defined_contribution_annual: 2000,
      },
      retirement_income_total_annual: 15000,
      desired_income_annual: 14000,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    await screen.findByText("Beth Example");
    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
    await userEvent.selectOptions(ownerSelect, "beth");
    expect(routeState.setSelectedOwner).toHaveBeenCalledWith("beth");

    const nowPanel = screen.getByRole("region", {
      name: /adjust the plan to match your life today/i,
    });
    const nowWithin = within(nowPanel);
    const careerPath = nowWithin.getByLabelText(/career path/i) as HTMLInputElement;
    expect(careerPath).toHaveAttribute("aria-valuetext", "Balanced pace");
    fireEvent.change(careerPath, { target: { value: "2" } });
    expect(careerPath).toHaveAttribute("aria-valuetext", "Accelerated path");

    fireEvent.change(ownerSelect, { target: { value: "beth" } });
    const monthlySavings = nowWithin.getByLabelText(/monthly savings/i);
    fireEvent.change(monthlySavings, { target: { value: "100" } });

    const monthlySpending = nowWithin.getByLabelText(
      /monthly spending in retirement/i,
    );
    fireEvent.change(monthlySpending, { target: { value: "3000" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await vi.waitFor(() =>
      expect(mockGetPensionForecast).toHaveBeenCalledWith(
        expect.objectContaining({
          owner: "beth",
          investmentGrowthPct: 7,
          contributionMonthly: 100,
          desiredIncomeAnnual: 36000,
        }),
      ),
    );
    const snapshot = screen.getByRole("region", {
      name: en.pensionForecast.header.heading,
    });
    const snapshotWithin = within(snapshot);
    expect(
      snapshotWithin.getByText(en.pensionForecast.header.pensionPot),
    ).toBeInTheDocument();
    expect(snapshotWithin.getByText("£123.00")).toBeInTheDocument();
    expect(
      snapshotWithin.getByText(en.pensionForecast.header.employeeContribution),
    ).toBeInTheDocument();
    expect(snapshotWithin.getByText("£100.00")).toBeInTheDocument();
    expect(
      snapshotWithin.getByText(en.pensionForecast.header.employerContribution),
    ).toBeInTheDocument();
    expect(
      snapshotWithin.getByText(
        en.pensionForecast.header.totalContribution.replace(
          "{{total}}",
          "£250.00",
        ),
      ),
    ).toBeInTheDocument();
    await screen.findByText(/birth date: 1990-01-01/i);
    const futurePanel = screen.getByRole("region", {
      name: /see what retirement could look like/i,
    });
    const futureWithin = within(futurePanel);
    expect(futureWithin.getByText(/pension pot/i)).toBeInTheDocument();
    expect(futureWithin.getByText("£123.00")).toBeInTheDocument();
    expect(futureWithin.getByText(/projected pot at 65/i)).toBeInTheDocument();
    expect(futureWithin.getByText("£323.00")).toBeInTheDocument();
    await screen.findByText("Retirement income breakdown");
    expect(
      screen.getByText(
        "You're on track: projected income of £15,000.00 meets your desired £14,000.00 — you could retire as early as age 64.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("State pension")).toBeInTheDocument();
    expect(screen.getByText("Defined benefit")).toBeInTheDocument();
    expect(screen.getByText("Defined contribution")).toBeInTheDocument();
    expect(screen.getByText("£9,000.00")).toBeInTheDocument();
    expect(screen.getByText("£750.00")).toBeInTheDocument();
    expect(screen.getByText("60%", { exact: false })).toBeInTheDocument();
    expect(
      screen.getByText("Total annual income: £15,000.00", { exact: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Total monthly income: £1,250.00", { exact: true }),
    ).toBeInTheDocument();
  });

  it("uses active route owner when available", async () => {
    routeState.selectedOwner = "beth";
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
      { owner: "beth", full_name: "Beth Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
      dob: null,
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
    await vi.waitFor(() => expect(ownerSelect).toHaveValue("beth"));
    expect(routeState.setSelectedOwner).not.toHaveBeenCalled();
  });

  it("defaults to first available owner when no active selection", async () => {
    routeState.selectedOwner = "";
    mockGetOwners.mockResolvedValue([
      { owner: "demo", full_name: "Demo", accounts: [] },
      { owner: "carol", full_name: "Carol Example", accounts: [] },
      { owner: "zoe", full_name: "Zoe Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
      dob: null,
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
    await vi.waitFor(() =>
      expect(routeState.setSelectedOwner).toHaveBeenCalledWith("carol"),
    );
    expect(ownerSelect).toHaveValue("carol");
  });

  it("shows shortfall insight when desired income is not met", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 50,
      pension_pot_gbp: 25,
      current_age: 40,
      retirement_age: 67,
      dob: "1984-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: {
        state_pension_annual: 6000,
        defined_benefit_annual: 0,
        defined_contribution_annual: 1000,
      },
      retirement_income_total_annual: 7000,
      desired_income_annual: 12000,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const monthlySpending = within(form).getByLabelText(/monthly spending in retirement/i);
    fireEvent.change(monthlySpending, { target: { value: "1000" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await screen.findByText(
      "Projected income leaves a shortfall of £5,000.00 per year (£416.67 per month) against your desired £12,000.00.",
    );
  });

  it("labels the earliest age without claiming the shortfall goes away (#7103)", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 50,
      pension_pot_gbp: 25,
      current_age: 40,
      retirement_age: 67,
      dob: "1984-01-01",
      earliest_retirement_age: 55,
      retirement_income_breakdown: {
        state_pension_annual: 6000,
        defined_benefit_annual: 0,
        defined_contribution_annual: 1000,
      },
      retirement_income_total_annual: 7000,
      desired_income_annual: 12000,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const monthlySpending = within(form).getByLabelText(
      /monthly spending in retirement/i,
    );
    fireEvent.change(monthlySpending, { target: { value: "1000" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    // This branch fires *because* projected income misses the target, so the
    // copy must not also promise the target is reached at that age.
    await screen.findByText(
      "You could retire as early as age 55, but your projected income leaves a shortfall of £5,000.00 per year (£416.67 per month) against your desired £12,000.00.",
    );
  });

  it("shows a plain-language message when death age is not after retirement age", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "steve", full_name: "Steve Leonard", accounts: [] },
    ]);
    mockGetPensionForecast.mockRejectedValue(
      new Error("death_age must exceed retirement_age"),
    );

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const deathAge = within(form).getByLabelText(/plan until age/i);
    fireEvent.change(deathAge, { target: { value: "50" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await screen.findByText(
      "Plan until age (50) must be after your retirement age.",
    );
    expect(
      screen.queryByText(/death_age must exceed retirement_age/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/^Error:/)).not.toBeInTheDocument();
  });

  it("names the retirement age in the error once it is known from a prior forecast", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "steve", full_name: "Steve Leonard", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValueOnce({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 55,
      retirement_age: 67,
      dob: "1970-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);
    await screen.findByText(/birth date: 1970-01-01/i);

    mockGetPensionForecast.mockRejectedValueOnce(
      new Error("death_age must exceed retirement_age"),
    );
    const deathAge = within(form).getByLabelText(/plan until age/i);
    fireEvent.change(deathAge, { target: { value: "50" } });
    await userEvent.click(btn);

    await screen.findByText(
      "Plan until age (50) must be after your retirement age (67).",
    );
  });

  it("falls back to generic input guidance for an unrecognised 400", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "steve", full_name: "Steve Leonard", accounts: [] },
    ]);
    const err = Object.assign(new Error("some_unmapped_detail"), {
      status: 400,
    });
    mockGetPensionForecast.mockRejectedValue(err);

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await screen.findByText(
      "We couldn't calculate this forecast. Please check your inputs and try again.",
    );
    expect(screen.queryByText(/some_unmapped_detail/)).not.toBeInTheDocument();
  });

  it("passes a backend-outage message through instead of blaming the user's inputs", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "steve", full_name: "Steve Leonard", accounts: [] },
    ]);
    // api.ts already replaces transient-status bodies with this copy; the page
    // must not overwrite it with "check your inputs" (#7131 review follow-up).
    const err = Object.assign(
      new Error(
        "The backend service is temporarily unavailable. Please try again.",
      ),
      { status: 503 },
    );
    mockGetPensionForecast.mockRejectedValue(err);

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await screen.findByText(
      "The backend service is temporarily unavailable. Please try again.",
    );
    expect(
      screen.queryByText(/check your inputs/i),
    ).not.toBeInTheDocument();
  });

  it("surfaces employer contribution adjustments", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 2500,
      current_age: 30,
      retirement_age: 65,
      dob: "1993-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const snapshot = await screen.findByRole("region", {
      name: en.pensionForecast.header.heading,
    });
    expect(snapshot).toBeInTheDocument();
    expect(
      within(snapshot).getByText(en.pensionForecast.header.noLinkedPots),
    ).toBeInTheDocument();
    const employerSlider = screen.getByLabelText(
      en.pensionForecast.employerContributionLabel,
    );
    fireEvent.change(employerSlider, { target: { value: "400" } });
    expect(
      within(snapshot).getByText(
        en.pensionForecast.header.totalContribution.replace(
          "{{total}}",
          "£650.00",
        ),
      ),
    ).toBeInTheDocument();
  });

  // #7211 + review follow-up: an ISA is not a pension, but nor is every
  // SIPP-shaped label backend-included -- "Accounts included in this
  // forecast" as a single heading over every account was itself a false
  // claim, since no account list is ever sent to the forecast endpoint and
  // the backend only counts accounts whose account_type contains "sipp"
  // (DEFINED_CONTRIBUTION_ACCOUNT_MARKERS in backend/common/pension.py).
  // The fix splits into two honest groups instead of tagging a single list,
  // and does not filter any account off the page.
  it("renders account types as ISA/SIPP (not raw slugs) and groups accounts by whether the backend actually counts them", async () => {
    mockGetOwners.mockResolvedValue([
      {
        owner: "alex",
        full_name: "Alex Example",
        // "workplace-sipp" is not an exact "sipp" match but the backend's
        // substring rule counts it -- this is the finding 2 regression case.
        accounts: ["isa", "sipp", "gia", "workplace-sipp"],
      },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const snapshot = await screen.findByRole("region", {
      name: en.pensionForecast.header.heading,
    });
    const snapshotWithin = within(snapshot);

    // Two honest groups instead of one implying every account is used. The
    // "region" is present from the very first render (static markup), so
    // wait for the owner -> accounts effect chain to actually settle before
    // asserting on anything that depends on it.
    await snapshotWithin.findByText("Used in this forecast");
    expect(
      snapshotWithin.getByText(
        "Other accounts (for reference -- not included in this forecast)",
      ),
    ).toBeInTheDocument();

    // Every account type is still present -- none filtered out.
    const sippChip = snapshotWithin.getByText("SIPP");
    const workplaceSippChip = await snapshotWithin.findByText("Workplace Sipp");
    const isaChip = snapshotWithin.getByText("ISA");
    const giaChip = snapshotWithin.getByText("GIA");
    expect(snapshotWithin.queryByText("isa")).not.toBeInTheDocument();
    expect(snapshotWithin.queryByText("sipp")).not.toBeInTheDocument();
    expect(snapshotWithin.queryByText("gia")).not.toBeInTheDocument();

    // SIPP and workplace-sipp (substring match, like the backend) land in
    // the "used" group; ISA and GIA land in "other".
    const usedGroup = sippChip.closest("div")!;
    const otherGroup = isaChip.closest("div")!;
    expect(within(usedGroup).getByText("SIPP")).toBeInTheDocument();
    expect(within(usedGroup).getByText("Workplace Sipp")).toBeInTheDocument();
    expect(within(otherGroup).getByText("ISA")).toBeInTheDocument();
    expect(within(otherGroup).getByText("GIA")).toBeInTheDocument();
    expect(workplaceSippChip.closest("div")).toBe(usedGroup);
    expect(giaChip.closest("div")).toBe(otherGroup);
  });

  it("seeds the current pension pot from portfolio data before a forecast is run (#7211)", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: ["isa", "sipp"] },
    ]);
    mockGetPortfolio.mockResolvedValue({
      owner: "alex",
      as_of: "2026-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 5200,
      accounts: [
        { account_type: "sipp", currency: "GBP", value_estimate_gbp: 4200, holdings: [] },
        { account_type: "isa", currency: "GBP", value_estimate_gbp: 1000, holdings: [] },
      ],
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const snapshot = await screen.findByRole("region", {
      name: en.pensionForecast.header.heading,
    });
    // Only the SIPP value counts toward the pension pot -- the ISA is not a
    // pension and must not be folded into the figure.
    await within(snapshot).findByText("£4,200.00");
    expect(
      within(snapshot).getByText("From your latest portfolio data"),
    ).toBeInTheDocument();
    expect(within(snapshot).queryByText(/not available/i)).not.toBeInTheDocument();
  });

  it("labels the pension pot as pending rather than 'Not available' when there's no portfolio pension data", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: ["isa"] },
    ]);
    mockGetPortfolio.mockResolvedValue({
      owner: "alex",
      as_of: "2026-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 1000,
      accounts: [
        { account_type: "isa", currency: "GBP", value_estimate_gbp: 1000, holdings: [] },
      ],
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const snapshot = await screen.findByRole("region", {
      name: en.pensionForecast.header.heading,
    });
    await within(snapshot).findByText("Shown after you run a forecast");
    expect(within(snapshot).queryByText(/^Not available$/)).not.toBeInTheDocument();
  });

  it("relabels 'Death age' to 'Plan until age' with a sensible default and guidance", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    expect(within(form).queryByText(/^Death age$/)).not.toBeInTheDocument();
    const planUntilAge = within(form).getByLabelText(/plan until age/i) as HTMLInputElement;
    expect(planUntilAge.value).toBe("90");
    expect(
      within(form).getByText(/how far into retirement to plan for/i),
    ).toBeInTheDocument();
  });

  it("gives the state pension input a default value and guidance, and gives the contribution sliders an explicit defaults note", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const statePension = within(form).getByLabelText(/state pension/i) as HTMLInputElement;
    expect(statePension.value).toBe("0");
    expect(
      within(form).getByText(/your expected annual state pension/i),
    ).toBeInTheDocument();
    expect(
      within(form).getAllByText(/starting example value/i).length,
    ).toBeGreaterThan(0);
  });

  // This only exercises the default-submit case -- it does NOT render the
  // blank-field case or compare two requests, so it can't by itself prove
  // "unchanged behaviour". What it does prove: the field's new default of
  // "0" is sent as an explicit statePensionAnnual: 0. The None-vs-0
  // equivalence on the wire is a backend fact, not something the frontend
  // can observe -- it's covered directly by
  // test_forecast_pension_none_state_pension_matches_explicit_zero in
  // tests/backend/common/test_pension.py (#7211 review follow-up).
  it("submits the default state pension value ('0') as an explicit statePensionAnnual: 0", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await vi.waitFor(() =>
      expect(mockGetPensionForecast).toHaveBeenCalledWith(
        expect.objectContaining({ statePensionAnnual: 0 }),
      ),
    );
  });

  // Ported from #7227's follow-up: the pot stat must distinguish "the
  // portfolio fetch is still in flight" from "loaded, no pension accounts" --
  // both previously fell through to the same "not available" copy.
  it("shows a loading state for the pension pot while the portfolio fetch is in flight", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: ["sipp"] },
    ]);
    let resolvePortfolio: (value: unknown) => void = () => {};
    mockGetPortfolio.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePortfolio = resolve;
        }),
    );

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const snapshot = await screen.findByRole("region", {
      name: en.pensionForecast.header.heading,
    });
    await within(snapshot).findByText(en.common.loading);
    expect(
      within(snapshot).queryByText(en.pensionForecast.header.notAvailable),
    ).not.toBeInTheDocument();

    // The pot effect only calls getPortfolio once the owner has actually
    // resolved (async, via getOwners) -- wait for that real call before
    // resolving it, otherwise this resolves a promise from a call that
    // hasn't happened yet and the later real call is left pending forever.
    await vi.waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alex"));

    resolvePortfolio({
      owner: "alex",
      as_of: "2026-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 4200,
      accounts: [
        { account_type: "sipp", currency: "GBP", value_estimate_gbp: 4200, holdings: [] },
      ],
    });

    await within(snapshot).findByText("£4,200.00");
  });

  // Ported from #7227's follow-up: a genuine fetch failure must be reported
  // as a load error, not silently misread as "no pension accounts".
  it("shows a load-error message for the pension pot when the portfolio fetch fails", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: ["sipp"] },
    ]);
    mockGetPortfolio.mockRejectedValue(new Error("network error"));

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const snapshot = await screen.findByRole("region", {
      name: en.pensionForecast.header.heading,
    });
    await within(snapshot).findByText(en.pensionForecast.header.loadError);
    expect(
      within(snapshot).queryByText(en.pensionForecast.header.notAvailable),
    ).not.toBeInTheDocument();
  });

  // Ported from #7227's follow-up: a forecast run for one owner must not
  // linger under a different owner selected afterwards.
  it("clears a previous owner's forecast result on a genuine owner switch", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
      { owner: "beth", full_name: "Beth Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 100,
      pension_pot_gbp: 999,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
    await vi.waitFor(() => expect(ownerSelect).toHaveValue("alex"));

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);
    await vi.waitFor(() =>
      expect(screen.getAllByText("£999.00").length).toBeGreaterThan(0),
    );

    fireEvent.change(ownerSelect, { target: { value: "beth" } });

    await vi.waitFor(() =>
      expect(screen.queryAllByText("£999.00")).toHaveLength(0),
    );
    expect(screen.queryByText(/birth date: 1990-01-01/i)).not.toBeInTheDocument();
  });
});

