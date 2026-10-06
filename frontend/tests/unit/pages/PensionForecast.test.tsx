import "@/setupTests";
import { render, screen, within, fireEvent, cleanup } from "@testing-library/react";
import type { ReactElement } from "react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import en from "@/locales/en/translation.json";

import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";

import { humanizeForecastError } from "@/utils/forecastErrors";

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
const mockGetPensionProfile = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    getOwners: mockGetOwners,
    getPensionForecast: mockGetPensionForecast,
    getPortfolio: mockGetPortfolio,
    getPensionProfile: mockGetPensionProfile,
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
    // Match src/i18n.ts -- React already escapes, so "2026/27" stays literal.
    interpolation: { escapeValue: false },
  });
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe("PensionForecast page", () => {
  beforeEach(() => {
    // Displayed ages are calendar ages derived from the DOB, so pin "today"
    // (only Date -- real timers keep userEvent/findBy* working).
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 6));
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
    // Default: no dob on file, so the form falls back to its "unknown" age
    // copy and leaves the retirement age for the backend to default.
    mockGetPensionProfile.mockRejectedValue(
      Object.assign(new Error("missing or invalid dob"), { status: 400 }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.useRealTimers();
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

  it("shows calendar age from the DOB rather than rounding the fractional age", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    // 2013-03-11 -> 2026-10-06 is 13.57 years; Math.round showed 14.
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 13.5715263518,
      retirement_age: 68,
      dob: "2013-03-11",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const btn = await screen.findByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await screen.findByText(/birth date: 2013-03-11/i);
    expect(screen.getByText("Current age: 13")).toBeInTheDocument();
    expect(screen.queryByText("Current age: 14")).not.toBeInTheDocument();
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
          // employee £100 + default employer £150
          contributionMonthly: 250,
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

  // Explicit coverage for the null-retirementAge path: this is the user's
  // *first* forecast attempt, so no prior successful forecast has populated
  // `retirementAge`. The error copy must therefore omit the parenthetical
  // retirement age entirely (contrast with the "names the retirement age"
  // test below, which mocks a prior successful forecast first).
  it("shows a plain-language message when death age is not after retirement age and no prior retirement age is known", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "steve", full_name: "Steve Leonard", accounts: [] },
    ]);
    // No prior successful forecast is mocked, so `retirementAge` stays null
    // when the death-age validation error comes back.
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

    // Plain-language copy with no parenthetical retirement age, because none
    // is known yet.
    await screen.findByText(
      "Death age (50) must be after your retirement age.",
    );
    expect(
      screen.queryByText(/must be after your retirement age \(/i),
    ).not.toBeInTheDocument();
    // Raw backend field names and Error: prefixes must never leak through.
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
      "Death age (50) must be after your retirement age (67).",
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
    const statePension = within(form).getByLabelText(/state pension \(/i) as HTMLInputElement;
    expect(statePension.value).toBe("12548");
    expect(
      within(form).getByText(/full new state pension for 2026\/27/i),
    ).toBeInTheDocument();
    expect(
      within(form).getAllByText(/starting example value/i).length,
    ).toBeGreaterThan(0);
  });

  it("caps your and your employer's contributions at the £5,000/month annual allowance combined", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const savings = screen.getByLabelText(/monthly savings/i) as HTMLInputElement;
    const employer = screen.getByLabelText(
      en.pensionForecast.employerContributionLabel,
    ) as HTMLInputElement;
    expect(savings).toHaveAttribute("max", "5000");
    expect(employer).toHaveAttribute("max", "5000");

    fireEvent.change(savings, { target: { value: "4000" } });
    expect(savings.value).toBe("4000");
    // Employer default is £150 -> asking for £2,000 is clamped to the £1,000 left.
    fireEvent.change(employer, { target: { value: "2000" } });
    expect(employer.value).toBe("1000");
    fireEvent.change(savings, { target: { value: "4500" } });
    expect(savings.value).toBe("4000");
    expect(
      screen.getByText(/you \+ employer: £5,000\.00 a month/i),
    ).toBeInTheDocument();

    // With the employer slider taking the whole allowance, savings clamp to £0.
    fireEvent.change(savings, { target: { value: "0" } });
    fireEvent.change(employer, { target: { value: "5000" } });
    expect(employer.value).toBe("5000");
    fireEvent.change(savings, { target: { value: "500" } });
    expect(savings.value).toBe("0");
  });

  it("doesn't flag a later State Pension when retiring at state pension age", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 46,
      retirement_age: 67,
      state_pension_age: 67,
      dob: "1980-06-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: {
        state_pension_annual: 12548,
        defined_benefit_annual: 0,
        defined_contribution_annual: 0,
      },
      retirement_income_total_annual: 12548,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    await userEvent.click(screen.getByRole("button", { name: /^forecast$/i }));
    await screen.findByText("Retirement income breakdown");
    expect(
      screen.queryByText(/state pension isn't paid until/i),
    ).not.toBeInTheDocument();
  });

  it("shows a profile load failure instead of passing it off as a missing date of birth", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    mockGetPensionProfile.mockRejectedValue(
      Object.assign(new Error("The backend service is temporarily unavailable."), {
        status: 503,
      }),
    );

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    expect(
      await screen.findByText(
        "Couldn't load age details: The backend service is temporarily unavailable.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(en.pensionForecast.ages.ageNowUnknown),
    ).not.toBeInTheDocument();
  });

  it("offers minimum/moderate/comfortable retirement spending presets for single and couple households", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const spending = screen.getByLabelText(
      /monthly spending in retirement/i,
    ) as HTMLInputElement;

    await userEvent.click(screen.getByRole("button", { name: /^moderate/i }));
    // £32,700/yr single -> £2,725/month, rounded to the slider's £10 step.
    expect(spending.value).toBe("2730");
    expect(screen.getByRole("button", { name: /^moderate/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await userEvent.click(screen.getByRole("button", { name: /^couple$/i }));
    await userEvent.click(screen.getByRole("button", { name: /^comfortable/i }));
    // £62,700/yr couple -> £5,225/month.
    expect(spending.value).toBe("5230");
    expect(screen.getByText(/£62,700\/year/)).toBeInTheDocument();
  });

  it("shows age now and defaults the retirement age to the state pension age, sending a changed age with the forecast", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", full_name: "Alex Example", accounts: [] },
    ]);
    mockGetPensionProfile.mockResolvedValue({
      dob: "1980-06-01",
      current_age: 46.3,
      state_pension_age: 67,
    });
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 46.3,
      retirement_age: 60,
      state_pension_age: 67,
      dob: "1980-06-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: {
        state_pension_annual: 0,
        defined_benefit_annual: 0,
        defined_contribution_annual: 1000,
      },
      retirement_income_total_annual: 1000,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("@/pages/PensionForecast");

    renderWithI18n(<PensionForecast />);

    const retirementAge = (await screen.findByDisplayValue("67")) as HTMLInputElement;
    expect(retirementAge).toBe(screen.getByLabelText(/^retirement age$/i));
    expect(screen.getByText("46")).toBeInTheDocument();
    expect(screen.getByText(/state pension age \(67\)/i)).toBeInTheDocument();
    expect(mockGetPensionProfile).toHaveBeenCalledWith("alex");

    fireEvent.change(retirementAge, { target: { value: "60" } });
    await userEvent.click(screen.getByRole("button", { name: /^forecast$/i }));

    await vi.waitFor(() =>
      expect(mockGetPensionForecast).toHaveBeenCalledWith(
        expect.objectContaining({ retirementAge: 60 }),
      ),
    );
    expect(
      await screen.findByText(/retiring at 60 means your state pension isn't paid until 67/i),
    ).toBeInTheDocument();
  });

  // The extraction of `humanizeForecastError` into `@/utils/forecastErrors`
  // is a pure refactor: the page's behaviour is unchanged, and these tests
  // exercise the shared utility directly so its contract stays pinned even
  // if the page stops calling it in the future.
  describe("humanizeForecastError (shared utility)", () => {
    it("maps the death_age/retirement_age detail to plain language with a known retirement age", () => {
      expect(
        humanizeForecastError("death_age must exceed retirement_age", {
          deathAge: 50,
          retirementAge: 67,
        }),
      ).toBe("Death age (50) must be after your retirement age (67).");
    });

    it("omits the retirement age when it is not yet known", () => {
      expect(
        humanizeForecastError("death_age must exceed retirement_age", {
          deathAge: 50,
          retirementAge: null,
        }),
      ).toBe("Death age (50) must be after your retirement age.");
    });

    it("trims the raw message before lookup so whitespace does not defeat the map", () => {
      expect(
        humanizeForecastError("  death_age must exceed retirement_age  ", {
          deathAge: 50,
          retirementAge: 67,
        }),
      ).toBe("Death age (50) must be after your retirement age (67).");
    });

    it("maps the missing/invalid dob detail to a profile-check message", () => {
      expect(
        humanizeForecastError("missing or invalid dob", {
          deathAge: 90,
          retirementAge: null,
        }),
      ).toBe(
        "We couldn't determine this owner's date of birth. Please check their profile details and try again.",
      );
    });

    it("falls back to generic input guidance for an unrecognised 4xx", () => {
      expect(
        humanizeForecastError("some_unmapped_detail", {
          deathAge: 90,
          retirementAge: null,
          status: 400,
        }),
      ).toBe(
        "We couldn't calculate this forecast. Please check your inputs and try again.",
      );
    });

    it("passes a 5xx message through instead of blaming the user's inputs", () => {
      expect(
        humanizeForecastError(
          "The backend service is temporarily unavailable. Please try again.",
          { deathAge: 90, retirementAge: null, status: 503 },
        ),
      ).toBe(
        "The backend service is temporarily unavailable. Please try again.",
      );
    });

    it("uses a generic fallback when the raw message is empty and no status is given", () => {
      expect(
        humanizeForecastError("   ", { deathAge: 90, retirementAge: null }),
      ).toBe("We couldn't calculate this forecast. Please try again.");
    });
  });

  it("submits the default state pension value as the full new State Pension", async () => {
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
        expect.objectContaining({ statePensionAnnual: 12548 }),
      ),
    );
  });
});

