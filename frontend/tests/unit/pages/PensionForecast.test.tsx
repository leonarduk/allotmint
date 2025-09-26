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

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    getOwners: mockGetOwners,
    getPensionForecast: mockGetPensionForecast,
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
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders owner selector", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
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

  it("submits with selected owner", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [] },
      { owner: "beth", accounts: [] },
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

    await screen.findByText("beth");
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
        "You're on track: projected income of £15,000.00 meets your desired £14,000.00 from age 64.",
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
      { owner: "alex", accounts: [] },
      { owner: "beth", accounts: [] },
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
      { owner: "demo", accounts: [] },
      { owner: "carol", accounts: [] },
      { owner: "zoe", accounts: [] },
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
    await vi.waitFor(() => expect(ownerSelect).toHaveValue("carol"));
    expect(routeState.setSelectedOwner).toHaveBeenCalledWith("carol");
  });

  it("shows shortfall insight when desired income is not met", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
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

  it("surfaces employer contribution adjustments and additional pensions", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
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
    const addButton = within(snapshot).getByRole("button", {
      name: en.pensionForecast.header.addAnother,
    });
    await userEvent.click(addButton);
    expect(
      within(snapshot).getByText(
        en.pensionForecast.header.additionalPensions_one.replace(
          "{{count}}",
          "1",
        ),
      ),
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
});

